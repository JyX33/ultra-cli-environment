# AI Reddit News Agent

An intelligent Python application that automates finding relevant Reddit discussions for a given topic and generates comprehensive Markdown reports with AI-powered summaries.

## 🚀 Features

- **Subreddit Discovery**: Automatically finds and ranks relevant subreddits for any topic
- **Content Filtering**: Fetches top posts sorted by engagement, filtering out media-only content
- **Web Scraping**: Extracts article content from external links
- **AI Summarization**: Generates concise summaries for both posts and community discussions
- **Report Generation**: Creates downloadable Markdown reports with structured content
- **RESTful API**: FastAPI-based endpoints for easy integration

## 📋 Prerequisites

- Python 3.9+
- Reddit API credentials
- OpenAI API key
- Docker (optional, for containerized deployment)

## 🛠️ Installation

### Option 1: Local Development

1. **Clone the repository**

   ```bash
   git clone <repository-url>
   cd ai_reddit_agent
   ```

2. **Install dependencies using uv (recommended)**

   ```bash
   uv sync
   ```

   Or using pip:

   ```bash
   pip install .
   ```

3. **Set up environment variables**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and add your credentials:

   ```env
   REDDIT_CLIENT_ID=your_reddit_client_id
   REDDIT_CLIENT_SECRET=your_reddit_client_secret
   REDDIT_USER_AGENT=YourApp/1.0 by YourUsername
   OPENAI_API_KEY=your_openai_api_key
   ```

4. **Run the application**

   ```bash
   uvicorn app.main:app --reload
   ```

### Option 2: Docker

1. **Build and run with Docker Compose**

   ```bash
   docker-compose up --build
   ```

   Or build manually:

   ```bash
   docker build -t ai-reddit-agent .
   docker run -p 8000:8000 --env-file .env ai-reddit-agent
   ```

## 📚 API Documentation

Once running, visit `http://localhost:8000/docs` for interactive API documentation.

### Endpoints

#### 1. Discover Subreddits

```http
GET /discover-subreddits/{topic}
```

**Purpose**: Find and rank relevant subreddits for a given topic.

**Example**:

```bash
curl http://localhost:8000/discover-subreddits/artificial-intelligence
```

**Response**:

```json
[
  {
    "name": "MachineLearning",
    "description": "A subreddit dedicated to learning machine learning",
    "score": 15
  },
  {
    "name": "artificial",
    "description": "Artificial Intelligence discussion",
    "score": 12
  }
]
```

#### 2. Generate Report

```http
GET /generate-report/{subreddit}/{topic}
```

**Purpose**: Generate a comprehensive Markdown report for a specific subreddit and topic.

**Example**:

```bash
curl http://localhost:8000/generate-report/MachineLearning/neural-networks -o report.md
```

**Response**: Downloads a Markdown file containing:

- Post summaries with AI-generated content analysis
- Community sentiment summaries from top comments
- Structured format with titles, links, and key insights

## 🏗️ Architecture

```
ai_reddit_agent/
├── app/
│   ├── core/
│   │   └── config.py          # Environment configuration
│   ├── services/
│   │   ├── reddit_service.py  # Reddit API interactions
│   │   ├── scraper_service.py # Web scraping functionality
│   │   └── summarizer_service.py # AI summarization
│   ├── utils/
│   │   ├── relevance.py       # Subreddit scoring logic
│   │   └── report_generator.py # Markdown report creation
│   └── main.py               # FastAPI application
├── tests/                    # Comprehensive test suite
├── Dockerfile               # Container configuration
├── docker-compose.yml       # Multi-service orchestration
└── pyproject.toml          # Project dependencies
```

## 🔧 Configuration

### Reddit API Setup

1. Go to [Reddit App Preferences](https://www.reddit.com/prefs/apps)
2. Click "Create App" or "Create Another App"
3. Choose "script" application type
4. Note your client ID and secret

### OpenAI API Setup

1. Visit [OpenAI API Keys](https://platform.openai.com/api-keys)
2. Create a new API key
3. Ensure you have sufficient credits/usage limits

## 🧪 Testing

Run the comprehensive test suite:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app

# Run specific test modules
pytest tests/services/test_reddit_service.py
```

## 🔄 Development Workflow

This project follows **Test-Driven Development (TDD)**:

1. **Write tests first** for new functionality
2. **Implement code** to pass the tests
3. **Refactor** while maintaining test coverage

### Key Testing Patterns

- **Service mocking**: All external APIs (Reddit, OpenAI) are mocked
- **Error handling**: Tests cover failure scenarios and edge cases
- **Integration tests**: Verify end-to-end workflow functionality

## 🚨 Error Handling

The application includes robust error handling:

- **API Rate Limits**: Automatic exponential backoff for Reddit API
- **Failed Scraping**: Graceful fallback with error messages
- **AI Service Failures**: Clear error reporting when summarization fails
- **No Results**: Specific error messages for empty result sets

## 📖 Usage Examples

### Basic Workflow

1. **Discover relevant subreddits**:

   ```bash
   curl http://localhost:8000/discover-subreddits/machine-learning
   ```

2. **Choose a subreddit and generate report**:

   ```bash
   curl http://localhost:8000/generate-report/MachineLearning/deep-learning -o ml_report.md
   ```

3. **Review the generated report** containing:
   - Top 5 posts from the last 24 hours (sorted by engagement)
   - AI-powered content summaries
   - Community sentiment analysis
   - Direct links to original discussions

### Advanced Usage

- **Niche Topics**: Works with specialized subjects and smaller communities
- **Batch Processing**: Use the API programmatically for multiple topics
- **Custom Integration**: Embed in larger data analysis pipelines

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Write tests for new functionality
4. Implement the feature
5. Ensure all tests pass: `pytest`
6. Submit a pull request

## 📜 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Troubleshooting

### Common Issues

**"Authentication failed"**

- Verify Reddit API credentials in `.env`
- Check that your Reddit app type is set to "script"

**"OpenAI API error"**

- Confirm your API key is valid and has available credits
- Check OpenAI service status

**"No posts found"**

- Try different subreddits or topics
- Verify the subreddit exists and has recent activity

**Docker build issues**

- Ensure Docker daemon is running
- Check that all required files are present

### Support

For issues and questions:

1. Check the [GitHub Issues](link-to-issues)
2. Review the API documentation at `/docs`
3. Ensure all environment variables are correctly set

## 🔮 Future Enhancements

- Support for multiple output formats (PDF, JSON)
- Real-time monitoring of subreddit discussions
- Advanced filtering and customization options
- Integration with additional AI providers
- Scheduled report generation
