AI Reddit News Agent: Project TODO Checklist
This checklist breaks down the development plan into actionable steps. Mark each item as you complete it.

✅ Prompt 1: Project Setup & Configuration
✅ Create the project directory structure (app, tests, etc.).
✅ Create pyproject.toml.
✅ Add all required dependencies to pyproject.toml (fastapi, praw, pytest, etc.).
✅ Create .env.example with all required API key placeholders.
✅ Create app/core/config.py to load environment variables.
✅ Create tests/core/test_config.py.
✅ Write a test to verify that the configuration is loaded correctly from mocked environment variables.

✅ Prompt 2: Reddit Service - Subreddit Discovery
✅ Create app/services/reddit_service.py.
✅ Create tests/services/test_reddit_service.py.
✅ In reddit_service.py, define the RedditService class.
✅ Implement the __init__ method to authenticate with the Reddit API using credentials from config.py.
✅ Implement the search_subreddits method.
✅ In test_reddit_service.py, write test_search_subreddits.
✅ Use pytest-mock to mock the praw.Reddit client within the test.
✅ Assert that the search_subreddits method calls the PRAW API correctly and returns the mocked data.

✅ Prompt 3: Subreddit Relevance Scoring
✅ Create app/utils/relevance.py.
✅ Create tests/utils/test_relevance.py.
✅ In reddit_service.py, add the get_hot_posts method.
✅ Write a unit test for get_hot_posts in test_reddit_service.py, using mocks.
✅ In relevance.py, define the score_and_rank_subreddits function.
✅ Implement the logic to iterate, call get_hot_posts, score based on keyword matching, and collect results.
✅ Implement the logic to sort the final list by score.
✅ In test_relevance.py, write test_score_and_rank_subreddits.
✅ Create mock subreddit and post objects for the test.
✅ Mock the RedditService and its get_hot_posts method.
✅ Assert that the function returns a correctly scored and sorted list.

✅ Prompt 4: Reddit Service - Post Fetching & Filtering
✅ In reddit_service.py, define the get_relevant_posts method.
✅ Implement logic to fetch top posts from the last day.
✅ Implement in-app sorting of fetched posts by num_comments.
✅ Implement the validation loop to filter out media posts/links.
✅ Implement the logic to collect exactly 5 valid posts.
✅ In test_reddit_service.py, write the test_get_relevant_posts test.
✅ Create a comprehensive list of mock posts (text, article links, media links) with varying comment counts.
✅ Mock the PRAW call to return this list.
✅ Assert that the returned list has a length of 5.
✅ Assert that the returned list contains no media posts.
✅ Assert that the returned list is correctly sorted by num_comments.

✅ Prompt 5: Web Scraping Service
✅ Create app/services/scraper_service.py.
✅ Create tests/services/test_scraper_service.py.
✅ In scraper_service.py, define the scrape_article_text function.
✅ Implement the function logic using requests and BeautifulSoup.
✅ Wrap the logic in a try...except block.
✅ Ensure the function returns the specific error message on failure.
✅ In test_scraper_service.py, write test_scrape_article_success.
✅ Mock requests.get to return a sample HTML structure.
✅ Assert the function extracts and joins text from <p> tags correctly.
✅ Write test_scrape_article_failure.
✅ Mock requests.get to raise an exception.
✅ Assert the function returns the correct error string.

✅ Prompt 6: AI Summarization Service
✅ Create app/services/summarizer_service.py.
✅ Create tests/services/test_summarizer_service.py.
✅ In summarizer_service.py, define the summarize_content function.
✅ Implement the logic to select a system prompt based on the prompt_type.
✅ Implement the openai.ChatCompletion.create API call.
✅ Wrap the logic in a try...except block.
✅ Ensure the function returns the specific error message on failure.
✅ In test_summarizer_service.py, write test_summarize_post_success.
✅ Mock openai.ChatCompletion.create to return a sample summary.
✅ Assert the function returns the correct summary.
✅ Write test_summarize_failure.
✅ Mock the API call to raise an exception.
✅ Assert the function returns the correct error string.

✅ Prompt 7: Report Generation Module
✅ Create app/utils/report_generator.py.
✅ Create tests/utils/test_report_generator.py.
✅ In report_generator.py, define the create_markdown_report function.
✅ Implement the logic to build the main Markdown report header.
✅ Implement the loop to generate the formatted section for each post in the data.
✅ In test_report_generator.py, write test_create_markdown_report.
✅ Create sample report data.
✅ Assert that the generated Markdown string contains the correct structure and data.

✅ Prompt 8: FastAPI Scaffolding and Main Workflow
✅ In app/main.py, import all necessary modules and services.
✅ Instantiate FastAPI and RedditService.
✅ In reddit_service.py, add the get_top_comments method and its corresponding unit test.
✅ In app/main.py, create the /discover-subreddits/{topic} GET endpoint.
✅ Implement the full orchestration logic for the discovery endpoint.
✅ In app/main.py, create the /generate-report/{subreddit}/{topic} GET endpoint.
✅ Implement the full orchestration logic for the report generation endpoint.
✅ Ensure the final report is returned as a downloadable file using StreamingResponse.

✅ Prompt 9: Dockerization
✅ Create Dockerfile in the project root.
✅ Define the base Python image.
✅ Add commands to copy and install dependencies.
✅ Add command to copy the application code.
✅ Add EXPOSE instruction for the application port.
✅ Add the CMD instruction to run uvicorn.
✅ (Optional) Create docker-compose.yml for simplified local execution.
