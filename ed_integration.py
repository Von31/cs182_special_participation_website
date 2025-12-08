"""
Ed Integration Backend for CS182A/282A Special Participation Portal
This script connects to Ed and streams posts to your database/API
"""

import os
import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional
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
    homework_number: Optional[int]
    llm_agent: Optional[str]
    timestamp: str
    url: str
    category: Optional[str]
    pdf_urls: Optional[List[str]]  # List of PDF/document URLs


class EdParticipationParser:
    """Parse Ed posts to extract participation information"""
    
    # Patterns to detect participation types and homework numbers
    PARTICIPATION_PATTERNS = {
        'A': r'\bparticipation\s*a\b|\bpart\s*a\b|\bpa\b',
        'B': r'\bparticipation\s*b\b|\bpart\s*b\b|\bpb\b',
        'C': r'\bparticipation\s*c\b|\bpart\s*c\b|\bpc\b',
        'D': r'\bparticipation\s*d\b|\bpart\s*d\b|\bpd\b',
    }
    
    HOMEWORK_PATTERN = r'\bhw\s*(\d+)\b|\bhomework\s*(\d+)\b'
    
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
        
        # Detect homework number
        hw_match = re.search(EdParticipationParser.HOMEWORK_PATTERN, text, re.IGNORECASE)
        if hw_match:
            hw_num = hw_match.group(1) or hw_match.group(2)
            result['homework_number'] = int(hw_num)
        
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
    
    async def send_to_api(self, endpoint: str, data: dict):
        """Send data to your backend API"""
        try:
            url = f"{self.api_base_url}/{endpoint}"
            async with self.session.post(url, json=data) as response:
                if response.status == 200 or response.status == 201:
                    print(f"✓ Sent data to {endpoint}")
                    return await response.json()
                else:
                    print(f"✗ Error sending to {endpoint}: {response.status}")
                    return None
        except Exception as e:
            print(f"✗ Error connecting to API: {e}")
            return None
    
    def extract_pdf_urls(self, thread) -> List[str]:
        """Extract PDF/document URLs from thread"""
        pdf_urls = []
        
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
        # Parse the post content
        category_name = ''
        if hasattr(thread, 'category') and thread.category:
            category_name = getattr(thread.category, 'name', '') if hasattr(thread.category, 'name') else str(thread.category)
        
        parsed = self.parser.parse_post(
            thread.title,
            thread.content or '',
            category_name
        )
        
        # Get author name
        author = 'Unknown'
        if hasattr(thread, 'user') and thread.user:
            if isinstance(thread.user, dict):
                author = thread.user.get('name', 'Unknown')
            elif hasattr(thread.user, 'name'):
                author = thread.user.name
        
        # Get post number
        post_number = None
        if hasattr(thread, 'number'):
            post_number = thread.number
        
        # Extract PDF URLs
        pdf_urls = self.extract_pdf_urls(thread)
        
        # Create EdPost object
        post = EdPost(
            post_id=thread.id,
            post_number=post_number,
            title=thread.title,
            author=author,
            content=thread.content or '',
            participation_type=parsed['participation_type'],
            homework_number=parsed['homework_number'],
            llm_agent=parsed['llm_agent'],
            timestamp=datetime.now().isoformat(),
            url=f"https://edstem.org/us/courses/{os.getenv('ED_COURSE_ID')}/discussion/{thread.id}",
            category=category_name if category_name else None,
            pdf_urls=pdf_urls if pdf_urls else None
        )
        
        return post
    
    async def handle_new_thread(self, thread):
        """Handle a new thread created on Ed"""
        print(f"\n📝 New thread detected: {thread.title}")
        
        # Process the thread
        post = self.process_thread(thread)
        
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
        if post.homework_number:
            print(f"   Homework: {post.homework_number}")
        if post.llm_agent:
            print(f"   LLM Agent: {post.llm_agent}")
        
        # Send to API
        await self.send_to_api('posts', asdict(post))
        
        # If this is a special participation post, also update student records
        if post.participation_type and post.homework_number and post.llm_agent:
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
        print(f"✏️  Thread updated: {thread.title}")
        post = self.process_thread(thread)
        await self.send_to_api(f'posts/{post.post_id}', asdict(post))
    
    async def handle_comment_create(self, comment):
        """Handle a new comment on a thread"""
        print(f"💬 New comment on thread {getattr(comment, 'thread_id', 'unknown')}")
        # You can add comment handling logic here if needed
    
    async def start_listening(self, course_id: str):
        """Start listening to Ed events"""
        print(f"\n{'='*60}")
        print(f"Starting Ed Integration for CS182A/282A")
        print(f"{'='*60}\n")
        print(f"Connecting to Ed course {course_id}...")
        
        # Start the client (subscribe will start listening)
        print("✓ Connected to Ed")
        print("✓ Listening for events...")
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
    
    if not course_id:
        print("ERROR: ED_COURSE_ID not found in environment variables!")
        print("Please add your course ID to the .env file")
        return
    
    # Create integration instance
    integration = EdIntegration(api_base_url=api_base_url)
    
    try:
        # Initialize
        await integration.initialize()
        
        # Start listening
        await integration.start_listening(course_id)
        
    except KeyboardInterrupt:
        print("\n\nShutting down gracefully...")
    except Exception as e:
        print(f"\nError: {e}")
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
    
    2. Install dependencies:
       - pip install aiohttp python-dotenv
       - Clone edpy: git clone https://github.com/bachtran02/edpy
    
    3. Make sure your backend API is running
    
    4. Run this script: python ed_integration.py
    """)
    
    asyncio.run(main())