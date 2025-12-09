"""
FastAPI Backend for CS182A/282A Special Participation Portal
This provides the API endpoints that your frontend expects
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
from typing import List, Optional, Dict, Union, Any
from datetime import datetime
import json

app = FastAPI(title="CS182A/282A Participation API")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage (replace with actual database in production)
# You should use PostgreSQL, MongoDB, or similar for production
class DataStore:
    def __init__(self):
        self.posts = []
        self.submissions = {}  # key: (student, homework, llm)
        self.students = set()
        self.homeworks = set()
        self.llms = set()
    
    def add_post(self, post_data: dict):
        """Add a new post"""
        # Check if post already exists
        existing = next((p for p in self.posts if p['post_id'] == post_data['post_id']), None)
        if existing:
            # Update existing post
            self.posts.remove(existing)
        
        self.posts.append(post_data)
        
        # Update sets
        if post_data.get('author'):
            self.students.add(post_data['author'])
        if post_data.get('homework_number'):
            # Include "N/A" in the homeworks set
            self.homeworks.add(str(post_data['homework_number']))
        if post_data.get('llm_agent'):
            self.llms.add(post_data['llm_agent'])
    
    def add_submission(self, submission_data: dict):
        """Add a new submission"""
        key = (
            submission_data.get('name'),
            str(submission_data.get('homework')),
            submission_data.get('llm')
        )
        self.submissions[key] = submission_data
        
        # Update sets
        if submission_data.get('name'):
            self.students.add(submission_data['name'])
        if submission_data.get('homework'):
            self.homeworks.add(str(submission_data['homework']))
        if submission_data.get('llm'):
            self.llms.add(submission_data['llm'])

# Global data store
db = DataStore()


# Pydantic models
class Post(BaseModel):
    class Config:
        # Allow arbitrary types to be validated by validators
        arbitrary_types_allowed = True
    
    post_id: int
    post_number: Optional[int] = None  # Post number from Ed
    title: str
    author: str
    content: str
    participation_type: Optional[str] = None
    homework_number: Optional[Any] = None  # Can be int or "N/A" - using Any to allow validator to handle it
    llm_agent: Optional[str] = None
    timestamp: str
    url: str
    category: Optional[str] = None
    pdf_urls: Optional[List[str]] = None  # List of PDF/document URLs
    
    @validator('homework_number', pre=True, always=True)
    def validate_homework_number(cls, v):
        """Accept int, "N/A", "unknown", or None for homework_number"""
        # Handle None
        if v is None:
            return None
        
        # Handle int - return as is
        if isinstance(v, int):
            return v
        
        # Handle string
        if isinstance(v, str):
            v_stripped = v.strip()
            v_lower = v_stripped.lower()
            v_upper = v_stripped.upper()
            # Check for N/A variations
            if v_upper == "N/A" or v_upper == "NA":
                return "N/A"
            # Check for unknown variations
            if v_lower == "unknown" or v_lower == "unk":
                return "unknown"
            # Empty string defaults to "unknown"
            if v_stripped == "":
                return "unknown"
            # Try to convert numeric string to int
            try:
                return int(v_stripped)
            except (ValueError, TypeError):
                # If conversion fails, return "unknown"
                return "unknown"
        
        # For any other type, try to convert to string first
        try:
            v_str = str(v).strip()
            v_lower = v_str.lower()
            v_upper = v_str.upper()
            if v_upper == "N/A" or v_upper == "NA":
                return "N/A"
            if v_lower == "unknown" or v_lower == "unk":
                return "unknown"
            if v_str == "":
                return "unknown"
            return int(v_str)
        except (ValueError, TypeError):
            return "unknown"


class Submission(BaseModel):
    name: str
    participation: str
    homework: int
    llm: str
    post_url: str
    timestamp: str


class StudentInfo(BaseModel):
    name: str


class HomeworkInfo(BaseModel):
    number: str
    students: List[str]
    llms: List[str]


class LLMInfo(BaseModel):
    name: str
    students: List[str]
    homeworks: List[str]


# API Endpoints

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "CS182A/282A Participation API",
        "stats": {
            "posts": len(db.posts),
            "submissions": len(db.submissions),
            "students": len(db.students),
            "homeworks": len(db.homeworks),
            "llms": len(db.llms)
        },
        "message": "If posts count is 0, make sure ed_integration.py is running and has received posts from Ed"
    }


@app.get("/api/students", response_model=List[StudentInfo])
async def get_students():
    """Get list of all students"""
    return [{"name": student} for student in sorted(db.students)]


@app.get("/api/homeworks", response_model=List[HomeworkInfo])
async def get_homeworks():
    """Get list of all homeworks with associated students and LLMs"""
    homeworks = []
    
    for hw in sorted(db.homeworks, key=lambda x: int(x) if x.isdigit() else 0):
        # Find all students and LLMs for this homework
        hw_students = set()
        hw_llms = set()
        
        for post in db.posts:
            if str(post.get('homework_number')) == hw:
                if post.get('author'):
                    hw_students.add(post['author'])
                if post.get('llm_agent'):
                    hw_llms.add(post['llm_agent'])
        
        homeworks.append({
            "number": hw,
            "students": list(hw_students),
            "llms": list(hw_llms)
        })
    
    return homeworks


@app.get("/api/llms", response_model=List[LLMInfo])
async def get_llms():
    """Get list of all LLM agents with associated students and homeworks"""
    llms = []
    
    for llm in sorted(db.llms):
        # Find all students and homeworks for this LLM
        llm_students = set()
        llm_homeworks = set()
        
        for post in db.posts:
            if post.get('llm_agent') == llm:
                if post.get('author'):
                    llm_students.add(post['author'])
                if post.get('homework_number'):
                    llm_homeworks.add(str(post['homework_number']))
        
        llms.append({
            "name": llm,
            "students": list(llm_students),
            "homeworks": list(llm_homeworks)
        })
    
    return llms


def generate_executive_summary(posts):
    """Generate an executive summary from post contents"""
    if not posts:
        return "No posts available to generate summary."
    
    # Combine all post contents
    all_content = " ".join([post.get('content', '') for post in posts if post.get('content')])
    
    if not all_content:
        return "No content available in posts to generate summary."
    
    # Simple summary generation (in production, use AI/LLM for better summaries)
    word_count = len(all_content.split())
    char_count = len(all_content)
    
    # Extract key information
    authors = set([post.get('author', 'Unknown') for post in posts])
    homeworks = set([str(post.get('homework_number', 'N/A')) for post in posts if post.get('homework_number')])
    llms = set([post.get('llm_agent', 'N/A') for post in posts if post.get('llm_agent')])
    participation_types = set([post.get('participation_type', 'N/A') for post in posts if post.get('participation_type')])
    
    # Generate summary
    summary = f"Executive Summary\n"
    summary += f"{'='*50}\n\n"
    summary += f"Overview:\n"
    summary += f"- Total Posts Analyzed: {len(posts)}\n"
    summary += f"- Total Content Length: {word_count:,} words, {char_count:,} characters\n"
    summary += f"- Authors: {', '.join(sorted(authors))}\n"
    summary += f"- Homework Assignments: {', '.join(sorted(homeworks, key=lambda x: int(x) if x.isdigit() else 0))}\n"
    summary += f"- LLM Agents Used: {', '.join(sorted(llms))}\n"
    summary += f"- Participation Types: {', '.join(sorted(participation_types))}\n\n"
    
    summary += f"Content Analysis:\n"
    # Extract first few sentences as key points
    sentences = all_content.split('.')[:5]
    summary += f"- Key Points: {' '.join([s.strip() for s in sentences if s.strip()])}\n\n"
    
    summary += f"Details:\n"
    for i, post in enumerate(posts[:3], 1):  # Summarize first 3 posts
        title = post.get('title', 'Untitled')
        author = post.get('author', 'Unknown')
        content_preview = post.get('content', '')[:200] + '...' if len(post.get('content', '')) > 200 else post.get('content', '')
        summary += f"{i}. {title} by {author}\n"
        summary += f"   {content_preview}\n\n"
    
    if len(posts) > 3:
        summary += f"... and {len(posts) - 3} more post(s)\n"
    
    return summary


@app.get("/api/submissions")
async def get_submission(
    student: str = Query(..., description="Student name"),
    homework: str = Query(..., description="Homework number"),
    llm: str = Query(..., description="LLM agent name")
):
    """Get a specific submission - generates summary from posts"""
    key = (student, homework, llm)
    submission = db.submissions.get(key)
    
    # Find matching posts
    matching_posts = [
        post for post in db.posts
        if post.get('author') == student
        and str(post.get('homework_number')) == str(homework)
        and post.get('llm_agent') == llm
    ]
    
    # Get PDF URLs from posts
    pdf_urls = []
    for post in matching_posts:
        if post.get('pdf_urls'):
            if isinstance(post['pdf_urls'], list):
                pdf_urls.extend(post['pdf_urls'])
            else:
                pdf_urls.append(post['pdf_urls'])
    
    # Generate summary from post contents
    summary = generate_executive_summary(matching_posts)
    
    # Use first PDF URL if available
    pdf_url = pdf_urls[0] if pdf_urls else None
    
    result = {
        "summary": summary,
        "pdfUrl": pdf_url,
        "pdfUrls": pdf_urls,  # All PDF URLs
        "student": student,
        "homework": homework,
        "llm": llm,
        "post_count": len(matching_posts)
    }
    
    # Merge with submission data if exists
    if submission:
        result.update(submission)
        if not result.get('summary'):
            result['summary'] = summary
    
    return result


@app.get("/api/posts")
async def get_posts(
    participation: Optional[str] = Query(None, description="Comma-separated participation types"),
    students: Optional[str] = Query(None, description="Comma-separated student names"),
    homeworks: Optional[str] = Query(None, description="Comma-separated homework numbers"),
    llms: Optional[str] = Query(None, description="Comma-separated LLM names")
):
    """Get filtered posts"""
    filtered_posts = db.posts.copy()
    
    # Parse comma-separated values
    if participation:
        part_list = [p.strip().upper() for p in participation.split(',')]
        filtered_posts = [p for p in filtered_posts if p.get('participation_type') in part_list]
    
    if students:
        student_list = [s.strip() for s in students.split(',')]
        filtered_posts = [p for p in filtered_posts if p.get('author') in student_list]
    
    if homeworks:
        hw_list = [h.strip() for h in homeworks.split(',')]
        filtered_posts = [
            p for p in filtered_posts 
            if p.get('homework_number') and 
            str(p.get('homework_number')) in hw_list
        ]
    
    if llms:
        llm_list = [l.strip() for l in llms.split(',')]
        filtered_posts = [p for p in filtered_posts if p.get('llm_agent') in llm_list]
    
    # Format for frontend - include all fields
    result = []
    for post in filtered_posts:
        result.append({
            "post_id": post.get('post_id'),
            "post_number": post.get('post_number'),
            "title": post.get('title', 'Untitled'),
            "author": post.get('author', 'Unknown'),
            "participation": post.get('participation_type', 'A'),
            "content": post.get('content', ''),
            "excerpt": post.get('content', '')[:150] + '...' if len(post.get('content', '')) > 150 else post.get('content', ''),
            "homework_number": post.get('homework_number'),
            "llm_agent": post.get('llm_agent'),
            "url": post.get('url', '#'),
            "pdf_urls": post.get('pdf_urls', []),
            "timestamp": post.get('timestamp', ''),
            "category": post.get('category')
        })
    
    return result


@app.get("/api/sentiment")
async def get_sentiment(
    students: Optional[str] = Query(None, description="Comma-separated student names"),
    homeworks: Optional[str] = Query(None, description="Comma-separated homework numbers"),
    llms: Optional[str] = Query(None, description="Comma-separated LLM names")
):
    """Get sentiment analysis data (mock data for now)"""
    # In production, this would calculate real sentiment from post content
    
    llm_list = llms.split(',') if llms else list(db.llms)
    
    sentiment_data = {}
    for llm in llm_list:
        llm = llm.strip()
        # Mock sentiment scores (in production, use actual NLP analysis)
        import random
        score = random.uniform(0.6, 0.95)
        sentiment = 'positive' if score > 0.75 else 'neutral' if score > 0.5 else 'negative'
        
        sentiment_data[llm] = {
            "score": score,
            "sentiment": sentiment
        }
    
    return sentiment_data


@app.post("/api/posts")
async def create_post(post: Post):
    """Create a new post (called by Ed integration)"""
    # Convert post to dict and handle "N/A" for homework_number
    post_dict = post.dict()
    # Keep "N/A" as string if that's what was sent
    db.add_post(post_dict)
    return {"status": "success", "post_id": post.post_id}


@app.post("/api/submissions")
async def create_submission(submission: Submission):
    """Create a new submission (called by Ed integration)"""
    db.add_submission(submission.dict())
    return {"status": "success"}


@app.put("/api/posts/{post_id}")
async def update_post(post_id: int, post: Post):
    """Update an existing post"""
    db.add_post(post.dict())
    return {"status": "success", "post_id": post_id}


# Add some initial demo data
@app.on_event("startup")
async def startup_event():
    """Add demo data on startup"""
    demo_posts = [
        {
            "post_id": 1,
            "title": "Participation A - HW1 using Claude",
            "author": "Alice Johnson",
            "content": "I used Claude to help debug my implementation...",
            "participation_type": "A",
            "homework_number": 1,
            "llm_agent": "Claude",
            "timestamp": datetime.now().isoformat(),
            "url": "https://edstem.org/us/courses/12345/discussion/1",
            "category": "Participation"
        },
        {
            "post_id": 2,
            "title": "Participation B - HW1 with ChatGPT",
            "author": "Bob Smith",
            "content": "ChatGPT helped me understand the algorithm...",
            "participation_type": "B",
            "homework_number": 1,
            "llm_agent": "ChatGPT",
            "timestamp": datetime.now().isoformat(),
            "url": "https://edstem.org/us/courses/12345/discussion/2",
            "category": "Participation"
        },
        {
            "post_id": 3,
            "title": "Participation C - HW2 Gemini assistance",
            "author": "Carol Williams",
            "content": "Gemini provided insights into optimization...",
            "participation_type": "C",
            "homework_number": 2,
            "llm_agent": "Gemini",
            "timestamp": datetime.now().isoformat(),
            "url": "https://edstem.org/us/courses/12345/discussion/3",
            "category": "Participation"
        }
    ]
    
    for post in demo_posts:
        db.add_post(post)
    
    print(f"\n✓ Demo data loaded: {len(demo_posts)} posts")
    print(f"✓ API ready at http://localhost:8320")
    print(f"✓ Docs available at http://localhost:8320/docs\n")


if __name__ == "__main__":
    import uvicorn
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║   CS182A/282A Participation API Server                     ║
    ╚════════════════════════════════════════════════════════════╝
    
    Starting server...
    - API: http://localhost:8320
    - Docs: http://localhost:8320/docs
    - Frontend should connect to: http://localhost:8320/api
    """)
    
    uvicorn.run(app, host="0.0.0.0", port=8320)