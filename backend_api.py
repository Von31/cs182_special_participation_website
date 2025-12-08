"""
FastAPI Backend for CS182A/282A Special Participation Portal
This provides the API endpoints that your frontend expects
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
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
    post_id: int
    title: str
    author: str
    content: str
    participation_type: Optional[str] = None
    homework_number: Optional[int] = None
    llm_agent: Optional[str] = None
    timestamp: str
    url: str
    category: Optional[str] = None


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
        }
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


@app.get("/api/submissions")
async def get_submission(
    student: str = Query(..., description="Student name"),
    homework: str = Query(..., description="Homework number"),
    llm: str = Query(..., description="LLM agent name")
):
    """Get a specific submission"""
    key = (student, homework, llm)
    submission = db.submissions.get(key)
    
    if not submission:
        # Return mock data for demo purposes
        return {
            "summary": f"Executive Summary for {student}'s Homework {homework} using {llm}:\n\n"
                      f"This is a placeholder summary. In production, this would contain:\n"
                      f"- Code quality analysis\n"
                      f"- Implementation approach\n"
                      f"- LLM agent interaction details\n"
                      f"- Performance metrics\n"
                      f"- Areas of improvement",
            "pdfUrl": None,
            "student": student,
            "homework": homework,
            "llm": llm
        }
    
    return submission


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
        filtered_posts = [p for p in filtered_posts if str(p.get('homework_number')) in hw_list]
    
    if llms:
        llm_list = [l.strip() for l in llms.split(',')]
        filtered_posts = [p for p in filtered_posts if p.get('llm_agent') in llm_list]
    
    # Format for frontend
    result = []
    for post in filtered_posts:
        result.append({
            "title": post.get('title', 'Untitled'),
            "author": post.get('author', 'Unknown'),
            "participation": post.get('participation_type', 'A'),
            "content": post.get('content', '')[:200] + '...' if len(post.get('content', '')) > 200 else post.get('content', ''),
            "excerpt": post.get('content', '')[:150] + '...' if len(post.get('content', '')) > 150 else post.get('content', ''),
            "url": post.get('url', '#')
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
    db.add_post(post.dict())
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