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
    title: str
    author: str
    content: str
    participation_type: Optional[str]  # A, B, C, or D
    homework_number: Optional[int]
    llm_agent: Optional[str]
    timestamp: str
    url: str
    category: Optional[str]


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


class EdIntegration:
    """Main integration class for Ed and the participation portal"""
    
    def __init__(self, api_base_url: str = 'http://localhost:8000/api'):
        self.api_base_url = api_base_url
        self.parser = EdParticipationParser()
        self.client = None
        self.session = None
        
    async def initialize(self):
        """Initialize the Ed client and HTTP session"""
        ed_token = os.getenv('ED_API_TOKEN')
        if not ed_token:
            raise ValueError("ED_API_TOKEN not found in environment variables")
        
        self.client = edpy.EdClient(ed_token=ed_token)
        self.session = aiohttp.ClientSession()
        print("✓ Ed client initialized")
    
    async def close(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()
    
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
    
    def process_thread(self, thread) -> EdPost:
        """Process an Ed thread and extract relevant information"""
        # Parse the post content
        parsed = self.parser.parse_post(
            thread.title,
            thread.content or '',
            getattr(thread.category, 'name', '') if hasattr(thread, 'category') else ''
        )
        
        # Create EdPost object
        post = EdPost(
            post_id=thread.id,
            title=thread.title,
            author=thread.user.get('name', 'Unknown') if hasattr(thread, 'user') else 'Unknown',
            content=thread.content or '',
            participation_type=parsed['participation_type'],
            homework_number=parsed['homework_number'],
            llm_agent=parsed['llm_agent'],
            timestamp=datetime.now().isoformat(),
            url=f"https://edstem.org/us/courses/{os.getenv('ED_COURSE_ID')}/discussion/{thread.id}",
            category=getattr(thread.category, 'name', None) if hasattr(thread, 'category') else None
        )
        
        return post
    
    async def handle_new_thread(self, thread):
        """Handle a new thread created on Ed"""
        print(f"\n📝 New thread detected: {thread.title}")
        
        # Process the thread
        post = self.process_thread(thread)
        
        # Print detected information
        print(f"   Author: {post.author}")
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
        print(f"💬 New comment on thread {comment.thread_id}")
        # You can add comment handling logic here if needed
    
    async def start_listening(self, course_id: str):
        """Start listening to Ed events"""
        print(f"\n{'='*60}")
        print(f"Starting Ed Integration for CS182A/282A")
        print(f"{'='*60}\n")
        print(f"Connecting to Ed course {course_id}...")
        
        # Register event handlers
        @self.client.event
        async def on_thread_create(thread):
            await self.handle_new_thread(thread)
        
        @self.client.event
        async def on_thread_update(thread):
            await self.handle_thread_update(thread)
        
        @self.client.event
        async def on_comment_create(comment):
            await self.handle_comment_create(comment)
        
        # Start the client
        print("✓ Connected to Ed")
        print("✓ Listening for events...")
        print(f"\n{'='*60}\n")
        
        try:
            await self.client.start(course_id)
        except Exception as e:
            print(f"Error in Ed listener: {e}")
            raise


async def main():
    """Main entry point"""
    # Get configuration from environment
    course_id = os.getenv('ED_COURSE_ID')
    api_base_url = os.getenv('API_BASE_URL', 'http://localhost:8000/api')
    
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
       - API_BASE_URL=http://localhost:8000/api
    
    2. Install dependencies:
       - pip install aiohttp python-dotenv
       - Clone edpy: git clone https://github.com/bachtran02/edpy
    
    3. Make sure your backend API is running
    
    4. Run this script: python ed_integration.py
    """)
    
    asyncio.run(main())