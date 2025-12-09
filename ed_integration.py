"""
Ed Integration Backend for CS182A/282A Special Participation Portal
This script connects to Ed and streams posts to your database/API
"""

import os
import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional, Union
from dotenv import load_dotenv
import re

# Import edpy (make sure you've cloned/installed the edpy library)
from edpy import edpy

# You'll need to install these additional packages
import aiohttp
from dataclasses import dataclass, asdict

# Load environment variables
load_dotenv()


@dataclass
class EdPost:
    """Data structure for Ed posts"""
    post_id: int
    post_number: Optional[int]  # Post number from Ed
    title: str
    author: str
    content: str
    participation_type: Optional[str]  # A, B, C, or D
    homework_number: Optional[Union[int, str]]  # Can be int or "N/A"
    llm_agent: Optional[str]
    timestamp: str
    url: str
    category: Optional[str]
    pdf_urls: Optional[List[str]]  # List of PDF/document URLs


class EdParticipationParser:
    """Parse Ed posts to extract participation information"""
    
    # Patterns to detect participation types and homework numbers
    PARTICIPATION_PATTERNS = {
        'A': r'\bParticipation\s*a\b|\bpart\s*a\b|\bpa\b',
        'B': r'\bParticipation\s*b\b|\bpart\s*b\b|\bpb\b',
        'C': r'\bParticipation\s*c\b|\bpart\s*c\b|\bpc\b',
        'D': r'\bParticipation\s*d\b|\bpart\s*d\b|\bpd\b',
    }
    
    HOMEWORK_PATTERN = r'\bhw\s*(\d+)\b|\bhomework\s*(\d+)\b|\bhw(\d+)\b'
    
    # Common LLM agent names
    LLM_PATTERNS = {
        'Claude': r'\bclaude\b',
        'ChatGPT': r'\bchatgpt\b|\bgpt-4\b|\bgpt\s*4\b',
        'GPT-3.5': r'\bgpt-3\.5\b|\bgpt\s*3\.5\b',
        'Gemini': r'\bgemini\b',
        'LLaMA': r'\bllama\b',
        'Mistral': r'\bmistral\b',
        'Copilot': r'\bcopilot\b',
    }
    
    @staticmethod
    def parse_post(title: str, content: str, category: str = '') -> Dict:
        """Extract participation info from post"""
        text = f"{title} {content} {category}".lower()
        
        result = {
            'participation_type': None,
            'homework_number': None,
            'llm_agent': None
        }
        
        # Detect participation type
        for part_type, pattern in EdParticipationParser.PARTICIPATION_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                result['participation_type'] = part_type
                break
        
        # Detect homework number - try multiple patterns
        hw_match = re.search(EdParticipationParser.HOMEWORK_PATTERN, text, re.IGNORECASE)
        if hw_match:
            # Try all capture groups
            hw_num = hw_match.group(1) or hw_match.group(2) or hw_match.group(3)
            if hw_num:
                try:
                    hw_int = int(hw_num)
                    # HW0 is valid, set to 0
                    result['homework_number'] = hw_int
                except (ValueError, TypeError):
                    pass
        
        # Also try uppercase HW pattern (case-insensitive should catch it, but just in case)
        if not result['homework_number']:
            hw_upper_match = re.search(r'HW\s*(\d+)', text, re.IGNORECASE)
            if hw_upper_match:
                try:
                    hw_int = int(hw_upper_match.group(1))
                    # HW0 is valid, set to 0
                    result['homework_number'] = hw_int
                except (ValueError, TypeError):
                    pass
        
        # Check if it's Special Participation E - if so, set to "N/A"
        if result['participation_type'] == 'E':
            result['homework_number'] = "N/A"
        # If no homework number found and not Participation E, set to "unknown"
        elif not result['homework_number']:
            result['homework_number'] = "unknown"
        
        # Detect LLM agent
        for llm_name, pattern in EdParticipationParser.LLM_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                result['llm_agent'] = llm_name
                break
        
        return result


class EdEventHandler:
    """Event handler class for Ed events using edpy listener pattern"""
    
    def __init__(self, integration: 'EdIntegration'):
        self.integration = integration
    
    @edpy.listener(edpy.ThreadNewEvent)
    async def on_thread_new(self, event: edpy.ThreadNewEvent):
        """Handle a new thread created on Ed"""
        await self.integration.handle_new_thread(event.thread)
    
    @edpy.listener(edpy.ThreadUpdateEvent)
    async def on_thread_update(self, event: edpy.ThreadUpdateEvent):
        """Handle a thread being updated"""
        await self.integration.handle_thread_update(event.thread)
    
    @edpy.listener(edpy.CommentNewEvent)
    async def on_comment_new(self, event: edpy.CommentNewEvent):
        """Handle a new comment on a thread"""
        await self.integration.handle_comment_create(event.comment)


class EdIntegration:
    """Main integration class for Ed and the participation portal"""
    
    def __init__(self, api_base_url: str = 'http://localhost:8320/api'):
        self.api_base_url = api_base_url
        self.parser = EdParticipationParser()
        self.client = None
        self.session = None
        self.event_handler = None
        
    async def initialize(self):
        """Initialize the Ed client and HTTP session"""
        ed_token = os.getenv('ED_API_TOKEN')
        if not ed_token:
            raise ValueError("ED_API_TOKEN not found in environment variables")
        
        self.client = edpy.EdClient(ed_token=ed_token)
        self.session = aiohttp.ClientSession()
        self.event_handler = EdEventHandler(self)
        self.client.add_event_hooks(self.event_handler)
        print("✓ Ed client initialized")
    
    async def close(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()
        # Note: edpy doesn't have a close method, but we can set is_subscribed to False
        if self.client:
            self.client.is_subscribed = False
    
    async def send_to_api(self, endpoint: str, data: dict, method: str = 'POST'):
        """Send data to your backend API"""
        try:
            url = f"{self.api_base_url}/{endpoint}"
            async with self.session.request(method=method, url=url, json=data) as response:
                if response.status == 200 or response.status == 201:
                    print(f"✓ Sent data to {endpoint}")
                    return await response.json()
                else:
                    error_text = await response.text()
                    print(f"✗ Error sending to {endpoint}: {response.status} - {error_text[:100]}")
                    return None
        except Exception as e:
            print(f"✗ Error connecting to API: {e}")
            return None
    
    def extract_pdf_urls(self, thread) -> List[str]:
        """Extract PDF/document URLs from thread"""
        pdf_urls = []
        
        # First, check content for PDF links in HTML
        if hasattr(thread, 'content') and thread.content:
            # Look for PDF links in HTML content
            pdf_link_pattern = r'href=["\']([^"\']*\.pdf[^"\']*)["\']|href=["\']([^"\']*edusercontent\.com[^"\']*)["\']'
            matches = re.finditer(pdf_link_pattern, thread.content, re.IGNORECASE)
            for match in matches:
                url = match.group(1) or match.group(2)
                if url and url not in pdf_urls:
                    pdf_urls.append(url)
        
        # Check the document field
        if hasattr(thread, 'document') and thread.document:
            # Document might be a URL string or JSON string
            if isinstance(thread.document, str):
                # Try to parse as JSON first
                try:
                    doc_data = json.loads(thread.document)
                    if isinstance(doc_data, dict):
                        # Look for URL or file fields
                        if 'url' in doc_data:
                            pdf_urls.append(doc_data['url'])
                        elif 'file' in doc_data:
                            pdf_urls.append(doc_data['file'])
                    elif isinstance(doc_data, list):
                        for item in doc_data:
                            if isinstance(item, dict):
                                if 'url' in item:
                                    pdf_urls.append(item['url'])
                                elif 'file' in item:
                                    pdf_urls.append(item['file'])
                except (json.JSONDecodeError, TypeError):
                    # If not JSON, might be a direct URL
                    if thread.document.startswith('http'):
                        pdf_urls.append(thread.document)
        
        # Check the raw data for attachments
        if hasattr(thread, '_raw') and thread._raw:
            raw_data = thread._raw
            # Check for attachments field
            if 'attachments' in raw_data:
                attachments = raw_data['attachments']
                if isinstance(attachments, list):
                    for att in attachments:
                        if isinstance(att, dict):
                            # Check if it's a PDF
                            file_type = att.get('type', '').lower()
                            file_name = att.get('name', '').lower()
                            if 'pdf' in file_type or file_name.endswith('.pdf'):
                                if 'url' in att:
                                    pdf_urls.append(att['url'])
                                elif 'file' in att:
                                    pdf_urls.append(att['file'])
            
            # Check for document field in raw data
            if 'document' in raw_data and raw_data['document']:
                doc = raw_data['document']
                if isinstance(doc, dict):
                    if 'url' in doc:
                        pdf_urls.append(doc['url'])
                    elif 'file' in doc:
                        pdf_urls.append(doc['file'])
                elif isinstance(doc, str) and doc.startswith('http'):
                    pdf_urls.append(doc)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_urls = []
        for url in pdf_urls:
            if url and url not in seen:
                seen.add(url)
                unique_urls.append(url)
        
        return unique_urls
    
    def process_thread(self, thread) -> EdPost:
        """Process an Ed thread and extract relevant information"""
        # Validate thread object
        if not thread:
            raise ValueError("Thread object is None or empty")
        
        # Get thread ID - check multiple sources
        thread_id = None
        if hasattr(thread, 'id') and thread.id:
            thread_id = thread.id
        elif hasattr(thread, '_raw') and thread._raw:
            thread_id = thread._raw.get('id') or thread._raw.get('thread_id')
            if thread_id:
                # Set the id attribute if it's missing
                if not hasattr(thread, 'id') or not thread.id:
                    thread.id = thread_id
        
        if not thread_id:
            raise ValueError("Cannot determine thread ID from thread object")
        
        # Also ensure user_id is set from raw data if missing
        if hasattr(thread, '_raw') and thread._raw:
            if not hasattr(thread, 'user_id') or not thread.user_id:
                user_id_from_raw = thread._raw.get('user_id')
                if user_id_from_raw:
                    thread.user_id = user_id_from_raw
        
        # Check if thread has minimal data (only ID and view_count)
        has_minimal_data = (
            hasattr(thread, '_raw') and 
            thread._raw and 
            len(thread._raw) <= 2 and 
            'id' in thread._raw
        )
        
        if has_minimal_data:
            print(f"⚠️  Warning: Thread {thread_id} has minimal data. Need to fetch full thread.")
            raise ValueError("Thread object is incomplete - needs full fetch")
        
        # Handle thread title - check multiple sources
        thread_title = getattr(thread, 'title', None)
        if not thread_title and hasattr(thread, '_raw') and thread._raw:
            thread_title = thread._raw.get('title')
        thread_title = thread_title or 'Untitled'
        
        # Handle thread content - check multiple sources
        thread_content = getattr(thread, 'content', None)
        if not thread_content and hasattr(thread, '_raw') and thread._raw:
            thread_content = thread._raw.get('content')
        thread_content = thread_content or ''
        
        # Parse the post content
        category_name = ''
        if hasattr(thread, 'category') and thread.category:
            category_name = getattr(thread.category, 'name', '') if hasattr(thread.category, 'name') else str(thread.category)
        
        parsed = self.parser.parse_post(
            thread_title,
            thread_content,
            category_name
        )
        
        # Get author name - check multiple sources
        author = 'Unknown'
        
        # First, try to get from thread.user object
        if hasattr(thread, 'user') and thread.user:
            if isinstance(thread.user, dict):
                author = thread.user.get('name', 'Unknown')
            elif hasattr(thread.user, 'name'):
                author = thread.user.name
            elif hasattr(thread.user, '__dict__'):
                # Try to get name from object attributes
                author = getattr(thread.user, 'name', 'Unknown')
        
        # If still Unknown, check raw data for user_id and try to get user info
        if author == 'Unknown' and hasattr(thread, '_raw') and thread._raw:
            raw_data = thread._raw
            
            # Check for user in raw data first
            if 'user' in raw_data:
                user_data = raw_data['user']
                if isinstance(user_data, dict):
                    author = user_data.get('name', 'Unknown')
                elif isinstance(user_data, str):
                    # Sometimes user might be just a name string
                    author = user_data
            
            # Check for user_name or author fields
            if author == 'Unknown':
                if 'user_name' in raw_data:
                    author = raw_data['user_name']
                elif 'author' in raw_data:
                    author_data = raw_data['author']
                    if isinstance(author_data, dict):
                        author = author_data.get('name', 'Unknown')
                    elif isinstance(author_data, str):
                        author = author_data
        
        # Debug: print if we can't find author (but don't spam)
        if author == 'Unknown':
            thread_id = getattr(thread, 'id', None) or (thread._raw.get('id') if hasattr(thread, '_raw') and thread._raw else None)
            print(f"⚠️  Warning: Could not extract author for thread {thread_id}")
            user_id = getattr(thread, 'user_id', None) or (thread._raw.get('user_id') if hasattr(thread, '_raw') and thread._raw else None)
            if user_id:
                print(f"   Thread user_id: {user_id}")
                print(f"   Note: User name should be in the users list from get_thread() response")
            if hasattr(thread, '_raw'):
                print(f"   Thread user attribute: {getattr(thread, 'user', 'Not found')}")
                print(f"   Raw data has user_id but no user object - need to match from users list")
        
        # Get post number
        post_number = None
        if hasattr(thread, 'number'):
            post_number = thread.number
        
        # Extract PDF URLs
        pdf_urls = self.extract_pdf_urls(thread)
        
        # Validate we have at least an ID before creating post
        if not thread.id:
            raise ValueError("Thread ID is required but missing")
        
        # Create EdPost object
        try:
            post = EdPost(
                post_id=thread.id,
                post_number=post_number,
                title=thread_title,
                author=author,
                content=thread_content,
                participation_type=parsed['participation_type'],
                homework_number=parsed['homework_number'],
                llm_agent=parsed['llm_agent'],
                timestamp=datetime.now().isoformat(),
                url=f"https://edstem.org/us/courses/{os.getenv('ED_COURSE_ID')}/discussion/{thread.id}",
                category=category_name if category_name else None,
                pdf_urls=pdf_urls if pdf_urls else None
            )
        except Exception as e:
            print(f"❌ Error creating EdPost object: {e}")
            print(f"   Thread ID: {thread.id}")
            print(f"   Thread title: {thread_title}")
            print(f"   Author: {author}")
            raise
        
        return post
    
    async def handle_new_thread(self, thread):
        """Handle a new thread created on Ed"""
        # Validate thread object first
        if not thread:
            print("❌ Error: Received empty thread object")
            return
        
        # Get thread ID from any available source
        thread_id = None
        if hasattr(thread, 'id') and thread.id:
            thread_id = thread.id
        elif hasattr(thread, '_raw') and thread._raw:
            thread_id = thread._raw.get('id') or thread._raw.get('thread_id')
        
        if not thread_id:
            print("❌ Error: Cannot determine thread ID")
            print(f"   Thread type: {type(thread)}")
            if hasattr(thread, '_raw'):
                print(f"   Raw data: {thread._raw}")
            return
        
        print(f"\n📝 New thread detected (ID: {thread_id})")
        
        # ALWAYS fetch full thread data - websocket events only send minimal data
        try:
            print(f"   Fetching full thread data for {thread_id}...")
            full_thread_data = await self.client.get_thread(thread_id)
            if full_thread_data and hasattr(full_thread_data, 'thread'):
                thread = full_thread_data.thread
                
                # Match user from users list if thread.user is not populated
                if (not hasattr(thread, 'user') or not thread.user) and hasattr(full_thread_data, 'users'):
                    # Get user_id from thread attribute or raw data
                    thread_user_id = getattr(thread, 'user_id', None)
                    if not thread_user_id and hasattr(thread, '_raw') and thread._raw:
                        thread_user_id = thread._raw.get('user_id')
                    
                    if thread_user_id:
                        print(f"   Looking for user with ID: {thread_user_id}")
                        for user in full_thread_data.users:
                            user_id = getattr(user, 'id', None)
                            if user_id == thread_user_id:
                                thread.user = user
                                print(f"   ✓ Matched user: {getattr(user, 'name', 'Unknown')}")
                                break
                        else:
                            print(f"   ⚠️  Could not find user {thread_user_id} in users list")
                            print(f"   Available user IDs: {[getattr(u, 'id', None) for u in full_thread_data.users]}")
                    else:
                        print(f"   ⚠️  No user_id found in thread")
                
                print(f"   ✓ Retrieved full thread data")
                print(f"   Title: {getattr(thread, 'title', 'N/A')}")
                author_name = 'N/A'
                if hasattr(thread, 'user') and thread.user:
                    if hasattr(thread.user, 'name'):
                        author_name = thread.user.name
                    elif isinstance(thread.user, dict):
                        author_name = thread.user.get('name', 'N/A')
                print(f"   Author: {author_name}")
            else:
                print(f"   ⚠️  Full thread data structure unexpected")
                print(f"   Type: {type(full_thread_data)}")
                if full_thread_data:
                    print(f"   Attributes: {dir(full_thread_data)[:10]}")
        except Exception as e:
            print(f"   ❌ Could not fetch full thread: {e}")
            import traceback
            traceback.print_exc()
            return  # Can't proceed without full data
        
        # Filter: Only process posts with "Special Participation" in the title
        thread_title = getattr(thread, 'title', None) or ''
        if 'Special Participation' not in thread_title:
            print(f"   ⏭️  Skipping thread (not a Special Participation post): {thread_title[:50]}...")
            return
        
        # Process the thread
        try:
            post = self.process_thread(thread)
        except ValueError as e:
            if "incomplete" in str(e).lower() or "needs full fetch" in str(e).lower():
                print(f"   Thread still incomplete after fetch, retrying...")
                # Try one more time
                try:
                    full_thread_data = await self.client.get_thread(thread_id)
                    if full_thread_data and hasattr(full_thread_data, 'thread'):
                        thread = full_thread_data.thread
                        post = self.process_thread(thread)
                    else:
                        print(f"   ❌ Still cannot get complete thread data")
                        return
                except Exception as e2:
                    print(f"   ❌ Retry failed: {e2}")
                    return
            else:
                print(f"❌ Error processing thread: {e}")
                import traceback
                traceback.print_exc()
                return
        except Exception as e:
            print(f"❌ Error processing thread: {e}")
            import traceback
            traceback.print_exc()
            return
        
        # Print detected information
        print(f"   Author: {post.author}")
        print(f"   Post Number: {post.post_number}")
        print(f"   Content: {post.content[:100]}..." if len(post.content) > 100 else f"   Content: {post.content}")
        if post.pdf_urls:
            print(f"   PDF Attachments: {len(post.pdf_urls)} file(s)")
            for i, pdf_url in enumerate(post.pdf_urls, 1):
                print(f"      {i}. {pdf_url}")
        if post.participation_type:
            print(f"   Participation Type: {post.participation_type}")
        if post.homework_number and post.homework_number != "N/A" and post.homework_number != "unknown":
            print(f"   Homework: {post.homework_number}")
        elif post.homework_number == "N/A":
            print(f"   Homework: N/A")
        elif post.homework_number == "unknown":
            print(f"   Homework: unknown")
        if post.llm_agent:
            print(f"   LLM Agent: {post.llm_agent}")
        else:
            print(f"   LLM Agent: Not detected (will show as 'Unknown' in UI)")
        
        # Send to API
        await self.send_to_api('posts', asdict(post))
        
        # If this is a special participation post, also update student records
        # Only create submission if homework is not "N/A" and not "unknown"
        if post.participation_type and post.homework_number and post.homework_number != "N/A" and post.homework_number != "unknown" and post.llm_agent:
            student_data = {
                'name': post.author,
                'participation': post.participation_type,
                'homework': post.homework_number,
                'llm': post.llm_agent,
                'post_url': post.url,
                'timestamp': post.timestamp
            }
            await self.send_to_api('submissions', student_data)
    
    async def handle_thread_update(self, thread):
        """Handle a thread being updated"""
        # Validate thread object
        if not thread:
            print("❌ Error: Received empty thread object in update")
            return
        
        # Get thread ID from any available source
        thread_id = None
        if hasattr(thread, 'id') and thread.id:
            thread_id = thread.id
        elif hasattr(thread, '_raw') and thread._raw:
            thread_id = thread._raw.get('id') or thread._raw.get('thread_id')
        
        if not thread_id:
            print("❌ Error: Thread update missing 'id' attribute")
            return
        
        print(f"✏️  Thread updated (ID: {thread_id})")
        
        # ALWAYS fetch full thread data for updates - websocket events only send minimal data
        try:
            print(f"   Fetching full thread data for update...")
            full_thread_data = await self.client.get_thread(thread_id)
            if full_thread_data and hasattr(full_thread_data, 'thread'):
                thread = full_thread_data.thread
                
                # Match user from users list if thread.user is not populated
                if (not hasattr(thread, 'user') or not thread.user) and hasattr(full_thread_data, 'users'):
                    # Get user_id from thread attribute or raw data
                    thread_user_id = getattr(thread, 'user_id', None)
                    if not thread_user_id and hasattr(thread, '_raw') and thread._raw:
                        thread_user_id = thread._raw.get('user_id')
                    
                    if thread_user_id:
                        for user in full_thread_data.users:
                            user_id = getattr(user, 'id', None)
                            if user_id == thread_user_id:
                                thread.user = user
                                break
                
                print(f"   ✓ Retrieved full thread data for update")
            else:
                print(f"   ⚠️  Could not get full thread data for update")
                return
        except Exception as e:
            print(f"   ❌ Could not fetch full thread for update: {e}")
            return
        
        # Filter: Only process posts with "Special Participation" in the title
        thread_title = getattr(thread, 'title', None) or ''
        # import ipdb; ipdb.set_trace()
        if 'Special Participation' not in thread_title:
            print(f"   ⏭️  Skipping thread update (not a Special Participation post): {thread_title[:50]}...")
            return
        
        # Process the thread update
        try:
            post = self.process_thread(thread)
            # Use PUT method for updates
            await self.send_to_api(f'posts/{post.post_id}', asdict(post), method='PUT')
        except Exception as e:
            print(f"✗ Error processing thread update: {e}")
            import traceback
            traceback.print_exc()
    
    async def handle_comment_create(self, comment):
        """Handle a new comment on a thread"""
        print(f"💬 New comment on thread {getattr(comment, 'thread_id', 'unknown')}")
        # You can add comment handling logic here if needed
    
    async def fetch_existing_posts(self, course_id: str, limit: int = 1000):
        """Fetch all existing Special Participation posts from Ed"""
        print(f"\n{'='*60}")
        print(f"Fetching existing Special Participation posts")
        print(f"{'='*60}\n")
        
        try:
            # Use the Ed API to fetch threads
            # The API endpoint is /api/courses/{course_id}/threads
            endpoint = f'/api/courses/{course_id}/threads'
            ed_token = os.getenv('ED_API_TOKEN')
            
            if not ed_token:
                print("❌ Error: ED_API_TOKEN not found")
                return []
            
            # Fetch threads with pagination
            all_threads = []
            page = 1
            per_page = 100  # Ed API typically returns 100 per page
            processed_count = 0
            
            while processed_count < limit:
                try:
                    # Make request to get threads using the transport's request method
                    # We'll use the client's transport to make authenticated requests
                    url = f"https://us.edstem.org{endpoint}?limit={per_page}&offset={(page-1)*per_page}"
                    
                    async with self.session.get(
                        url,
                        headers={'Authorization': ed_token}
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            print(f"   ⚠️  API returned status {response.status}: {error_text[:100]}")
                            if response.status == 404:
                                print(f"   Trying alternative endpoint format...")
                                # Try alternative endpoint
                                url = f"https://us.edstem.org/api/threads?course_id={course_id}&limit={per_page}&offset={(page-1)*per_page}"
                                async with self.session.get(url, headers={'Authorization': ed_token}) as alt_response:
                                    if alt_response.status != 200:
                                        break
                                    data = await alt_response.json()
                            else:
                                break
                        else:
                            data = await response.json()
                        
                        # Handle different response formats
                        threads = data.get('threads', [])
                        if not threads and isinstance(data, list):
                            threads = data
                        
                        if not threads:
                            print(f"   No more threads found (page {page})")
                            break
                        
                        print(f"   Fetched page {page}: {len(threads)} threads")
                        
                        # Filter for Special Participation posts
                        special_posts = [
                            t for t in threads 
                            if t.get('title', '') and 'Special Participation' in t.get('title', '')
                        ]
                        
                        print(f"   Found {len(special_posts)} Special Participation posts on this page")
                        
                        # Process each Special Participation post
                        for thread_data in special_posts:
                            try:
                                thread_id = thread_data.get('id')
                                if not thread_id:
                                    continue
                                
                                # Fetch full thread data to ensure we have all fields
                                try:
                                    full_thread_data = await self.client.get_thread(thread_id)
                                    if full_thread_data and hasattr(full_thread_data, 'thread'):
                                        thread = full_thread_data.thread
                                        
                                        # Match user from users list if thread.user is not populated
                                        if (not hasattr(thread, 'user') or not thread.user) and hasattr(full_thread_data, 'users'):
                                            # Get user_id from thread attribute or raw data
                                            thread_user_id = getattr(thread, 'user_id', None)
                                            if not thread_user_id and hasattr(thread, '_raw') and thread._raw:
                                                thread_user_id = thread._raw.get('user_id')
                                            
                                            if thread_user_id:
                                                for user in full_thread_data.users:
                                                    user_id = getattr(user, 'id', None)
                                                    if user_id == thread_user_id:
                                                        thread.user = user
                                                        break
                                    else:
                                        # Fallback: create thread from data
                                        thread = edpy.Thread(thread_data, **thread_data)
                                except Exception as fetch_error:
                                    print(f"   ⚠️  Could not fetch full data for {thread_id}, using available data: {fetch_error}")
                                    thread = edpy.Thread(thread_data, **thread_data)
                                
                                # Process the thread
                                post = self.process_thread(thread)
                                
                                # Send to API
                                await self.send_to_api('posts', asdict(post))
                                
                                # Also create submission if it has all required fields
                                # Only create submission if homework is not "N/A"
                                if post.participation_type and post.homework_number and post.homework_number != "N/A" and post.homework_number != "unknown" and post.llm_agent:
                                    student_data = {
                                        'name': post.author,
                                        'participation': post.participation_type,
                                        'homework': post.homework_number,
                                        'llm': post.llm_agent,
                                        'post_url': post.url,
                                        'timestamp': post.timestamp
                                    }
                                    await self.send_to_api('submissions', student_data)
                                
                                print(f"   ✓ Processed: {post.title[:50]}...")
                                processed_count += 1
                                
                            except Exception as e:
                                print(f"   ✗ Error processing thread {thread_data.get('id', 'unknown')}: {e}")
                                import traceback
                                traceback.print_exc()
                                continue
                        
                        all_threads.extend(special_posts)
                        
                        # Check if we've reached the limit or no more pages
                        if len(threads) < per_page or processed_count >= limit:
                            break
                        
                        page += 1
                        
                except Exception as e:
                    print(f"   ✗ Error fetching page {page}: {e}")
                    import traceback
                    traceback.print_exc()
                    break
            
            print(f"\n✓ Finished fetching existing posts")
            print(f"   Total Special Participation posts found: {len(all_threads)}")
            print(f"   Successfully processed: {processed_count}")
            return all_threads
            
        except Exception as e:
            print(f"❌ Error fetching existing posts: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def start_listening(self, course_id: str, fetch_existing: bool = True):
        """Start listening to Ed events"""
        print(f"\n{'='*60}")
        print(f"Starting Ed Integration for CS182A/282A")
        print(f"{'='*60}\n")
        print(f"Connecting to Ed course {course_id}...")
        
        # Optionally fetch existing posts first
        if fetch_existing:
            await self.fetch_existing_posts(course_id)
        
        # Start the client (subscribe will start listening)
        print("\n✓ Connected to Ed")
        print("✓ Listening for new events...")
        print(f"\n{'='*60}\n")
        
        try:
            await self.client.subscribe(int(course_id))
        except Exception as e:
            print(f"Error in Ed listener: {e}")
            raise


async def main():
    """Main entry point"""
    # Get configuration from environment
    course_id = os.getenv('ED_COURSE_ID')
    api_base_url = os.getenv('API_BASE_URL', 'http://localhost:8320/api')
    fetch_existing = os.getenv('FETCH_EXISTING_POSTS', 'true').lower() == 'true'
    
    if not course_id:
        print("ERROR: ED_COURSE_ID not found in environment variables!")
        print("Please add your course ID to the .env file")
        return
    
    # Create integration instance
    integration = EdIntegration(api_base_url=api_base_url)
    
    try:
        # Initialize
        await integration.initialize()
        
        # Start listening (and optionally fetch existing posts)
        await integration.start_listening(course_id, fetch_existing=fetch_existing)
        
    except KeyboardInterrupt:
        print("\n\nShutting down gracefully...")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await integration.close()
        print("✓ Integration stopped")


if __name__ == '__main__':
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║   CS182A/282A Ed Integration                               ║
    ║   Real-time participation tracking from EdStem             ║
    ╚════════════════════════════════════════════════════════════╝
    
    Setup Instructions:
    1. Create a .env file with:
       - ED_API_TOKEN=your-ed-token
       - ED_COURSE_ID=your-course-id
       - API_BASE_URL=http://localhost:8320/api
       - FETCH_EXISTING_POSTS=true (optional, defaults to true)
    
    2. Install dependencies:
       - pip install aiohttp python-dotenv
       - Clone edpy: git clone https://github.com/bachtran02/edpy
    
    3. Make sure your backend API is running
    
    4. Run this script: python ed_integration.py
    
    Features:
    - Fetches all existing "Special Participation" posts on startup
    - Listens for new "Special Participation" posts in real-time
    - Only processes posts with "Special Participation" in the title
    """)
    
    asyncio.run(main())