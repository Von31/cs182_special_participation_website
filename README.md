# CS182A/282A Ed Integration with Participation Portal

This project integrates EdStem with your Special Participation Search Portal, automatically streaming posts and tracking student participation in real-time.

## 🏗️ Architecture

```
┌─────────────┐
│   EdStem    │
│   (Ed API)  │
└──────┬──────┘
       │ WebSocket
       │ Events
       ↓
┌─────────────────────┐
│  ed_integration.py  │
│  (Event Listener)   │
└──────┬──────────────┘
       │ HTTP POST
       ↓
┌─────────────────────┐
│   backend_api.py    │
│   (FastAPI Server)  │
└──────┬──────────────┘
       │ REST API
       ↓
┌─────────────────────┐
│   Frontend HTML     │
│  (Your Portal UI)   │
└─────────────────────┘
```

## 📁 Project Structure

```
cs182a-ed-integration/
├── ed_integration.py      # Listens to Ed events
├── backend_api.py         # FastAPI server for frontend
├── index.html             # Your participation portal UI
├── requirements.txt       # Python dependencies
├── .env.example          # Environment variables template
├── .env                  # Your credentials (create this)
├── run.sh                # Startup script
├── edpy/                 # Ed API library (cloned)
└── README.md             # This file
```

## 🚀 Quick Start

### 1. Clone the Repository & Setup

```bash
# Clone or create your project directory
mkdir cs182a-ed-integration
cd cs182a-ed-integration

# Copy all the provided Python files to this directory
# - ed_integration.py
# - backend_api.py
# - requirements.txt
# - .env.example
# - run.sh
# - index.html (your existing portal)

# Clone the edpy library
git clone https://github.com/bachtran02/edpy.git
```

### 2. Configure Environment Variables

```bash
# Copy the example env file
cp .env.example .env

# Edit .env and add your credentials
nano .env  # or use your preferred editor
```

Required variables:
- `ED_API_TOKEN`: Get from https://edstem.org/us/settings/api-tokens
- `ED_COURSE_ID`: Find in your course URL (e.g., `/courses/12345/`)
- `API_BASE_URL`: Usually `http://localhost:8000/api`

### 3. Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install packages
pip install -r requirements.txt
```

### 4. Start the Services

**Option A: Using the startup script (recommended)**
```bash
chmod +x run.sh
./run.sh
```

**Option B: Manual startup**
```bash
# Terminal 1: Start the backend API
python backend_api.py

# Terminal 2: Start the Ed integration
python ed_integration.py

# Terminal 3: Serve the frontend (if needed)
python -m http.server 3000
```

### 5. Open Your Frontend

Navigate to `http://localhost:3000` (or wherever you're serving your HTML file)

## 📊 How It Works

### 1. Ed Integration (`ed_integration.py`)

This script connects to Ed using WebSockets and listens for events:

- **New Thread Created**: Parses the post to extract:
  - Participation type (A, B, C, D)
  - Homework number
  - LLM agent used (Claude, ChatGPT, Gemini, etc.)
  - Student name
  
- **Thread Updated**: Updates existing post data

- **Comments**: Optionally tracks comments on threads

### 2. Backend API (`backend_api.py`)

Provides REST endpoints for your frontend:

```
GET  /api/students          # List all students
GET  /api/homeworks         # List all homeworks
GET  /api/llms              # List all LLM agents
GET  /api/posts             # Get filtered posts
GET  /api/submissions       # Get specific submission
GET  /api/sentiment         # Get sentiment analysis
POST /api/posts             # Create new post (from Ed)
POST /api/submissions       # Create submission (from Ed)
```

### 3. Frontend Integration

Your existing HTML just needs to point to the correct API URL. The `API_BASE_URL` constant should be:

```javascript
const API_BASE_URL = 'http://localhost:8000/api';
```

## 🔍 Post Parsing Rules

The integration automatically detects participation info using these patterns:

### Participation Types
- **Type A**: Matches "participation a", "part a", "pa"
- **Type B**: Matches "participation b", "part b", "pb"  
- **Type C**: Matches "participation c", "part c", "pc"
- **Type D**: Matches "participation d", "part d", "pd"

### Homework Numbers
- Matches "HW 1", "Homework 1", "hw1", etc.

### LLM Agents
- **Claude**: "claude"
- **ChatGPT**: "chatgpt", "gpt-4", "gpt 4"
- **GPT-3.5**: "gpt-3.5", "gpt 3.5"
- **Gemini**: "gemini"
- **LLaMA**: "llama"
- **Mistral**: "mistral"
- **Copilot**: "copilot"

## 📝 Example Ed Post Format

For best automatic detection, students should format posts like:

```
Title: Participation A - HW1 using Claude

Content: I used Claude to help debug my implementation...
```

Or in the category: "Participation A"

## 🛠️ Customization

### Adding New LLM Patterns

Edit `ed_integration.py`:

```python
LLM_PATTERNS = {
    'Claude': r'\bclaude\b',
    'NewLLM': r'\bnewllm\b',  # Add your pattern
}
```

### Changing Participation Detection

Modify the `PARTICIPATION_PATTERNS` dict in `EdParticipationParser`.

### Using a Real Database

Replace the in-memory `DataStore` in `backend_api.py` with:

**PostgreSQL:**
```python
from databases import Database
database = Database("postgresql://user:password@localhost/dbname")
```

**MongoDB:**
```python
from motor.motor_asyncio import AsyncIOMotorClient
client = AsyncIOMotorClient("mongodb://localhost:27017")
db = client.cs182a
```

## 🐛 Troubleshooting

### "ED_API_TOKEN not found"
- Make sure you created `.env` file (not `.env.example`)
- Check that the token is valid at https://edstem.org/us/settings/api-tokens

### "Failed to connect to API"
- Ensure backend API is running (`python backend_api.py`)
- Check that port 8000 is not in use
- Verify `API_BASE_URL` in frontend matches backend

### "No posts appearing"
- Check that Ed integration is running
- Verify your course ID is correct
- Look at terminal output for errors
- Test by creating a post on Ed

### CORS Errors
- Make sure backend has CORS middleware enabled
- Check browser console for specific error
- Verify frontend is using correct API URL

## 📈 Production Deployment

For production use:

1. **Use a real database** (PostgreSQL, MongoDB)
2. **Set up proper authentication** (JWT tokens, API keys)
3. **Configure CORS properly** (specific origins, not "*")
4. **Use environment-specific configs**
5. **Add logging and monitoring**
6. **Deploy backend** (Heroku, AWS, DigitalOcean)
7. **Deploy frontend** (Netlify, Vercel, GitHub Pages)
8. **Use HTTPS** for all connections

Example production `.env`:
```bash
ED_API_TOKEN=your-token
ED_COURSE_ID=12345
API_BASE_URL=https://your-api.herokuapp.com/api
DATABASE_URL=postgresql://...
```

## 🔒 Security Notes

- **Never commit `.env`** to git (add to `.gitignore`)
- **Keep Ed API token secret**
- **Use HTTPS in production**
- **Validate all user input**
- **Rate limit API endpoints**
- **Use authentication** for sensitive data

## 🤝 Contributing

To add features:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📚 API Documentation

Once running, visit http://localhost:8000/docs for interactive API documentation (Swagger UI).

## 📞 Support

For issues related to:
- **edpy library**: https://github.com/bachtran02/edpy/issues
- **Ed API**: Contact Ed support
- **This integration**: Check logs and error messages

## 📄 License

This integration code is provided as-is for educational purposes.

---

**Happy tracking! 🎓**