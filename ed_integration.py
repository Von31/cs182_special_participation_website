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

# Import edpy (local package in edpy/ folder)
import edpy

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
    participation_type: Optional[str]  # A, B, C, D, or E
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
        'E': r'\bParticipation\s*e\b|\bpart\s*e\b|\bpe\b|\bSpecial\s+Participation\s+E\b',
    }
    
    HOMEWORK_PATTERN = r'\bhw\s*(\d+)\b|\bhomework\s*(\d+)\b|\bhw(\d+)\b'
    
    # Common LLM agent names
    LLM_PATTERNS = {
        'Claude': r'\bclaude\b',
        'ChatGPT': r'\bchatgpt\b|\bgpt-4\b|\bgpt\s*4\b',
        'GPT-3.5': r'\bgpt-3\.5\b|\bgpt\s*3\.5\b',
        'GPT-4o': r'\bgpt-4o\b|\bgpt\s*4o\b',
        'GPT-5.1': r'\bgpt-5\.1\b|\bgpt\s*5\.1\b',
        'Gemini': r'\bgemini\b',
        'LLaMA': r'\bllama\b',
        'Mistral': r'\bmistral\b',
        'Copilot': r'\bcopilot\b',
        'Grok': r'\bgrok\b',
        'Qwen': r'\bqwen\b',
        'Kimi': r'\bkimi\b',
        'DeepSeek': r'\bdeepseek\b',
        'Windsurf': r'\bwindsurf\b',
        'Perplexity': r'\bperplexity\b',
        'Cursor': r'\bcursor\b',
        'Nano Banana': r'\bnano banana\b',
        'GPT-Oss': r'\bgpt-oss\b',
        'Gemini Opus': r'\bopus\b'
        
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
        
        # Detect participation type FIRST (including E)
        for part_type, pattern in EdParticipationParser.PARTICIPATION_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                result['participation_type'] = part_type
                break
        
        # If it's Participation E, set homework to "N/A" and skip homework detection
        if result['participation_type'] == 'E':
            result['homework_number'] = "N/A"
        else:
            # Detect homework number - try multiple patterns (only if not Participation E)
            hw_match = re.search(EdParticipationParser.HOMEWORK_PATTERN, text, re.IGNORECASE)
            if hw_match:
                # Try all capture groups
                hw_num = hw_match.group(1) or hw_match.group(2) or hw_match.group(3)
                if hw_num:
                    try:
                        hw_int = int(hw_num)
                        # HW0 is valid, set to 0 (treat it like any other homework number)
                        result['homework_number'] = hw_int
                    except (ValueError, TypeError):
                        pass
            
            # Also try uppercase HW pattern (case-insensitive should catch it, but just in case)
            # Use explicit None check to handle 0 correctly (0 is falsy but valid)
            if result['homework_number'] is None:
                hw_upper_match = re.search(r'HW\s*(\d+)', text, re.IGNORECASE)
                if hw_upper_match:
                    try:
                        hw_int = int(hw_upper_match.group(1))
                        # HW0 is valid, set to 0 (treat it like any other homework number)
                        result['homework_number'] = hw_int
                    except (ValueError, TypeError):
                        pass
            
            # If no homework number found and not Participation E, set to "unknown"
            # Use explicit None check to handle 0 correctly (0 is falsy but valid)
            if result['homework_number'] is None:
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
        """Extract PDF/document URLs from thread - prioritize attached PDFs"""
        pdf_urls = []
        
        # Debug: Print raw data structure to understand Ed's format
        if hasattr(thread, '_raw') and thread._raw:
            raw_data = thread._raw
            print(f"   🔍 Debug: Raw data keys: {list(raw_data.keys())}")
            
            # PRIORITY 1: Check for attachments field (primary source for attached PDFs)
            if 'attachments' in raw_data:
                attachments = raw_data['attachments']
                print(f"   🔍 Debug: Found attachments field with {len(attachments) if isinstance(attachments, list) else 'non-list'} items")
                if isinstance(attachments, list):
                    for att in attachments:
                        print(f"   🔍 Debug: Attachment: {att}")
                        if isinstance(att, dict):
                            # Extract URL from various possible fields
                            url = None
                            # Try different URL field names
                            for url_field in ['url', 'file', 'file_url', 'download_url', 'src', 'href', 'link']:
                                if url_field in att and att[url_field]:
                                    url = att[url_field]
                                    print(f"   🔍 Debug: Found URL in '{url_field}': {url[:80]}...")
                                    break
                            
                            # If no URL found, try to construct from file_id or id
                            if not url:
                                file_id = att.get('file_id') or att.get('id')
                                if file_id:
                                    # Construct Ed URL for file
                                    url = f"https://us.edstem.org/api/files/{file_id}"
                                    print(f"   🔍 Debug: Constructed URL from file_id: {url}")
                            
                            if url:
                                # Check if it's a PDF by extension or type
                                file_type = att.get('type', '').lower()
                                file_name = att.get('name', '').lower() or att.get('filename', '').lower()
                                mime_type = att.get('mime_type', '').lower() or att.get('content_type', '').lower()
                                
                                # Accept if it's explicitly a PDF or has .pdf extension
                                is_pdf = (
                                    'pdf' in file_type or 
                                    file_name.endswith('.pdf') or 
                                    'pdf' in mime_type or
                                    'application/pdf' in mime_type
                                )
                                
                                # Also check if URL contains .pdf
                                if not is_pdf and url:
                                    is_pdf = '.pdf' in url.lower()
                                
                                if is_pdf and url not in pdf_urls:
                                    pdf_urls.append(url)
                                    print(f"   ✓ Added PDF from attachments: {url[:60]}...")
            
            # Check for document field in raw data
            if 'document' in raw_data and raw_data['document']:
                doc = raw_data['document']
                print(f"   🔍 Debug: Found document field: {type(doc)}")
                if isinstance(doc, dict):
                    print(f"   🔍 Debug: Document dict keys: {list(doc.keys())}")
                    # Try various URL fields
                    for url_field in ['url', 'file', 'file_url', 'download_url', 'src']:
                        if url_field in doc and doc[url_field]:
                            url = doc[url_field]
                            if url not in pdf_urls:
                                pdf_urls.append(url)
                                print(f"   ✓ Added PDF from document: {url[:60]}...")
                            break
                elif isinstance(doc, str) and doc.startswith('http'):
                    if doc not in pdf_urls:
                        pdf_urls.append(doc)
                        print(f"   ✓ Added PDF from document string: {doc[:60]}...")
            
            # Check for files field (alternative to attachments)
            if 'files' in raw_data:
                files = raw_data['files']
                print(f"   🔍 Debug: Found files field with {len(files) if isinstance(files, list) else 'non-list'} items")
                if isinstance(files, list):
                    for file_item in files:
                        print(f"   🔍 Debug: File item: {file_item}")
                        if isinstance(file_item, dict):
                            url = file_item.get('url') or file_item.get('file') or file_item.get('file_url') or file_item.get('src')
                            if url and url not in pdf_urls:
                                # Check if it's a PDF
                                file_name = file_item.get('name', '').lower() or file_item.get('filename', '').lower()
                                if '.pdf' in file_name or file_item.get('type', '').lower() == 'pdf' or '.pdf' in url.lower():
                                    pdf_urls.append(url)
                                    print(f"   ✓ Added PDF from files: {url[:60]}...")
        
        # PRIORITY 2: Check the document field on thread object
        if hasattr(thread, 'document') and thread.document:
            print(f"   🔍 Debug: Thread has document attribute: {type(thread.document)}")
            # Document might be a URL string or JSON string
            if isinstance(thread.document, str):
                # Try to parse as JSON first
                try:
                    doc_data = json.loads(thread.document)
                    if isinstance(doc_data, dict):
                        # Look for URL or file fields
                        for url_field in ['url', 'file', 'file_url', 'download_url']:
                            if url_field in doc_data and doc_data[url_field]:
                                if doc_data[url_field] not in pdf_urls:
                                    pdf_urls.append(doc_data[url_field])
                                    print(f"   ✓ Added PDF from thread.document JSON: {doc_data[url_field][:60]}...")
                                break
                    elif isinstance(doc_data, list):
                        for item in doc_data:
                            if isinstance(item, dict):
                                for url_field in ['url', 'file', 'file_url', 'download_url']:
                                    if url_field in item and item[url_field]:
                                        if item[url_field] not in pdf_urls:
                                            pdf_urls.append(item[url_field])
                                        break
                except (json.JSONDecodeError, TypeError):
                    # If not JSON, might be a direct URL
                    if thread.document.startswith('http') and thread.document not in pdf_urls:
                        pdf_urls.append(thread.document)
        
        # PRIORITY 3: Check content for PDF links in HTML
        # Ed uses various URL patterns for files
        content_to_check = []
        if hasattr(thread, 'content') and thread.content:
            content_to_check.append(('content', thread.content))
        if hasattr(thread, 'text') and thread.text:
            content_to_check.append(('text', thread.text))
        if hasattr(thread, '_raw') and thread._raw:
            if 'content' in thread._raw and thread._raw['content']:
                content_to_check.append(('raw_content', thread._raw['content']))
            if 'text' in thread._raw and thread._raw['text']:
                content_to_check.append(('raw_text', thread._raw['text']))
        
        for field_name, content in content_to_check:
            if not content:
                continue
            
            # Pattern 1: Standard PDF links with .pdf extension
            pdf_patterns = [
                # PRIORITY: Google Drive file URLs
                r'href=["\']?(https?://drive\.google\.com/file/d/[^"\'\s>]+)["\']?',
                r'(https?://drive\.google\.com/file/d/[^\s"\'<>]+)',
                # Ed static content URLs (static.us.edusercontent.com/files)
                r'href=["\']?(https?://static\.us\.edusercontent\.com/files/[^"\'\s>]+)["\']?',
                r'href=["\']([^"\']*\.pdf[^"\']*)["\']',
                # Pattern 2: Ed file URLs (static.us.edstem.org, edusercontent.com)
                r'href=["\']([^"\']*(?:static\.us\.edstem\.org|edusercontent\.com|edstem\.org/api/files)[^"\']*)["\']',
                # Pattern 3: Anchor tags with download attribute
                r'<a[^>]*href=["\']([^"\']+)["\'][^>]*download[^>]*>',
                # Pattern 4: File attachment links (Ed often uses data attributes)
                r'data-(?:file-)?url=["\']([^"\']+\.pdf[^"\']*)["\']',
                # Pattern 5: Direct Ed file API URLs
                r'(https?://(?:us\.)?edstem\.org/api/files/[^\s"\'<>]+)',
                # Pattern 6: Static Ed URLs
                r'(https?://static\.(?:us\.)?edstem\.org/[^\s"\'<>]+)',
                # Pattern 7: Ed user content URLs (covers all edusercontent patterns)
                r'(https?://static\.us\.edusercontent\.com/files/[^\s"\'<>]+)',
            ]
            
            for pattern in pdf_patterns:
                matches = re.finditer(pattern, content, re.IGNORECASE)
                for match in matches:
                    url = match.group(1)
                    if url and url not in pdf_urls:
                        # Clean up URL (remove trailing quotes, spaces, >)
                        url = re.sub(r'["\'\s>]+$', '', url).strip()
                        # Verify it looks like a PDF URL, Ed file URL, or Google Drive URL
                        if '.pdf' in url.lower() or 'edstem.org/api/files' in url.lower() or 'edstem.org' in url.lower() or 'edusercontent.com/files' in url.lower() or 'drive.google.com/file' in url.lower():
                            if url not in pdf_urls:
                                pdf_urls.append(url)
                                print(f"   ✓ Added PDF from {field_name} (pattern match): {url[:80]}...")
            
            # Also look for Ed-specific attachment classes
            # Ed uses <a class="file-attachment"> or <div class="attachment">
            attachment_patterns = [
                r'class=["\'][^"\']*(?:file-attachment|attachment|file)[^"\']*["\'][^>]*href=["\']([^"\']+)["\']',
                r'href=["\']([^"\']+)["\'][^>]*class=["\'][^"\']*(?:file-attachment|attachment|file)[^"\']*["\']',
                # Look for any anchor with PDF in the text
                r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>[^<]*\.pdf[^<]*</a>',
            ]
            
            for pattern in attachment_patterns:
                matches = re.finditer(pattern, content, re.IGNORECASE)
                for match in matches:
                    url = match.group(1)
                    if url and url not in pdf_urls:
                        pdf_urls.append(url)
                        print(f"   ✓ Added file from {field_name} (attachment class): {url[:60]}...")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_urls = []
        for url in pdf_urls:
            if url and url not in seen:
                seen.add(url)
                unique_urls.append(url)
        
        if unique_urls:
            print(f"   📎 Found {len(unique_urls)} PDF attachment(s)")
            for i, url in enumerate(unique_urls, 1):
                print(f"      {i}. {url[:80]}...")
        else:
            print(f"   📎 No PDF attachments found")
        
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
        
        # Handle thread content - prioritize document field for rich content
        thread_content = None
        
        # PRIORITY 1: Check for document field (Ed stores rich HTML content here)
        if hasattr(thread, 'document') and thread.document:
            print(f"   📄 Found thread.document field")
            if isinstance(thread.document, str):
                # Document is HTML string - use it directly
                thread_content = thread.document
                print(f"   📄 Using thread.document as content ({len(thread_content)} chars)")
        
        # Also check raw data for document
        if not thread_content and hasattr(thread, '_raw') and thread._raw:
            raw_doc = thread._raw.get('document')
            if raw_doc:
                print(f"   📄 Found raw_data['document'] field: {type(raw_doc)}")
                if isinstance(raw_doc, str):
                    thread_content = raw_doc
                    print(f"   📄 Using raw document as content ({len(thread_content)} chars)")
                elif isinstance(raw_doc, dict):
                    # Document might be a dict with content field
                    doc_content = raw_doc.get('content') or raw_doc.get('html') or raw_doc.get('body')
                    if doc_content:
                        thread_content = doc_content
                        print(f"   📄 Using document.content as content ({len(thread_content)} chars)")
        
        # PRIORITY 2: Check thread.text (Ed's text version of content)
        if not thread_content:
            thread_content = getattr(thread, 'text', None)
            if not thread_content and hasattr(thread, '_raw') and thread._raw:
                thread_content = thread._raw.get('text')
            if thread_content:
                print(f"   📄 Using thread.text as content ({len(thread_content)} chars)")
        
        # PRIORITY 3: Try content field as fallback
        if not thread_content:
            thread_content = getattr(thread, 'content', None)
            if not thread_content and hasattr(thread, '_raw') and thread._raw:
                thread_content = thread._raw.get('content')
            if thread_content:
                print(f"   📄 Using thread.content as content ({len(thread_content)} chars)")
        
        # PRIORITY 4: Try body field
        if not thread_content:
            thread_content = getattr(thread, 'body', None)
            if not thread_content and hasattr(thread, '_raw') and thread._raw:
                thread_content = thread._raw.get('body')
            if thread_content:
                print(f"   📄 Using thread.body as content ({len(thread_content)} chars)")
        
        # Ensure we have content - use title as last resort
        thread_content = thread_content or ''
        
        # Debug: Print all available fields in raw data
        if hasattr(thread, '_raw') and thread._raw:
            print(f"   🔍 Available raw fields: {list(thread._raw.keys())}")
        
        # If content is HTML, we might want to strip tags or keep them
        # For now, keep the raw content as it comes from Ed
        
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
            # Ensure content is not None - use title as fallback only if content is truly empty
            # But prefer to keep the actual thread.content even if it seems empty
            if not thread_content:
                thread_content = thread_title  # Use title as fallback if content is completely missing
            elif isinstance(thread_content, str) and thread_content.strip() == '':
                # Content exists but is empty string - still use it (might be intentional)
                # Only use title if we really have no content at all
                pass  # Keep empty string - it's valid content
            
            # Ensure we're using thread.text (prioritized) or thread.content as fallback
            final_content = str(thread_content) if thread_content else thread_title
            
            # Debug: Print content info
            print(f"   📄 Thread text/content extracted: {len(final_content)} characters")
            if final_content and len(final_content) > 0:
                print(f"   📄 Content preview: {final_content[:150]}...")
            else:
                print(f"   ⚠️  Warning: Thread text/content is empty, using title as fallback")
            
            post = EdPost(
                post_id=thread.id,
                post_number=post_number,
                title=thread_title,
                author=author,
                content=final_content,  # Use thread.text (prioritized) or thread.content as fallback
                participation_type=parsed['participation_type'],
                homework_number=parsed['homework_number'],
                llm_agent=parsed['llm_agent'],
                timestamp=datetime.now().isoformat(),
                url=f"https://edstem.org/us/courses/{os.getenv('ED_COURSE_ID')}/discussion/{thread.id}",
                category=category_name if category_name else None,
                pdf_urls=pdf_urls if pdf_urls else []  # Always use list, never None
            )
        except Exception as e:
            print(f"❌ Error creating EdPost object: {e}")
            print(f"   Thread ID: {thread.id}")
            print(f"   Thread title: {thread_title}")
            print(f"   Author: {author}")
            print(f"   Content length: {len(thread_content) if thread_content else 0}")
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
        if 'Special Participation' not in thread_title or 'Participation' not in thread_title:
            print(f"   ⏭️  Skipping thread (not a Special Participation or Participation related post): {thread_title[:50]}...")
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
        print(f"   Content length: {len(post.content) if post.content else 0} characters")
        print(f"   Content preview: {post.content[:200] if post.content and len(post.content) > 200 else (post.content if post.content else 'No content')}...")
        if post.pdf_urls:
            print(f"   PDF Attachments: {len(post.pdf_urls)} file(s)")
            for i, pdf_url in enumerate(post.pdf_urls, 1):
                print(f"      {i}. {pdf_url}")
        if post.participation_type:
            print(f"   Participation Type: {post.participation_type}")
        # Handle homework_number - check explicitly for None to handle 0 correctly
        if post.homework_number is not None and post.homework_number != "N/A" and post.homework_number != "unknown":
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
        # Use explicit None check to handle 0 correctly (0 is falsy but valid)
        if (post.participation_type and 
            post.homework_number is not None and 
            post.homework_number != "N/A" and 
            post.homework_number != "unknown" and 
            post.llm_agent):
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
                                # Only create submission if homework is not "N/A" and not "unknown"
                                # Use explicit None check to handle 0 correctly (0 is falsy but valid)
                                if (post.participation_type and 
                                    post.homework_number is not None and 
                                    post.homework_number != "N/A" and 
                                    post.homework_number != "unknown" and 
                                    post.llm_agent):
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