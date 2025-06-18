# AI Reddit News Agent: Test-Driven Prompt Plan

This document contains the full sequence of prompts for a code-generation LLM to build the "AI Reddit News Agent" application. The prompts follow a strict, test-driven development (TDD) methodology, ensuring each piece of functionality is tested before it's implemented.

---

### Prompt 1: Project Setup & Configuration

I am starting a new Python project for the "AI Reddit News Agent". The project will use FastAPI, PRAW, BeautifulSoup4, Requests, and the OpenAI library.

1. Create the basic project directory structure:

    ```
    ai_reddit_agent/
    ├── app/
    │   ├── __init__.py
    │   ├── main.py
    │   ├── services/
    │   │   ├── __init__.py
    │   ├── core/
    │   │   ├── __init__.py
    │   │   └── config.py
    │   └── utils/
    │       └── __init__.py
    ├── tests/
    │   ├── __init__.py
    │   └── core/
    │       ├── __init__.py
    │       └── test_config.py
    ├── .env.example
    └── pyproject.toml
    ```

2. Populate `pyproject.toml` with the necessary dependencies: `python = "^3.9"`, `fastapi`, `uvicorn`, `praw`, `requests`, `beautifulsoup4`, `openai`, and `python-dotenv`. For development, include `pytest` and `pytest-mock`.

3. Create a `.env.example` file with placeholders for `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`, and `OPENAI_API_KEY`.

4. In `app/core/config.py`, create a class or function using `python-dotenv` to load these environment variables. Ensure they are loaded upon module import.

5. In `tests/core/test_config.py`, write a pytest test using `pytest-mock`'s `monkeypatch` to set environment variables and assert that your config module loads them correctly.

---

### Prompt 2: Reddit Service - Subreddit Discovery

Based on our previous setup, I will now create the Reddit service.

1. Create a new file: `app/services/reddit_service.py`.
2. Create a corresponding test file: `tests/services/test_reddit_service.py`.

3. In `app/services/reddit_service.py`:
    * Import the configuration from `app.core.config`.
    * Import `praw`.
    * Define a class `RedditService`.
    * The `__init__` method should initialize an authenticated `praw.Reddit` client using the credentials from the config.
    * Define a method `search_subreddits(self, topic: str, limit: int = 10) -> list`. This method should use `self.reddit.subreddits.search(topic, limit=limit)` and return a list of subreddit objects.

4. In `tests/services/test_reddit_service.py`:
    * Write a test `test_search_subreddits`.
    * Inside the test, use `mocker.patch('praw.Reddit')` to mock the entire PRAW library.
    * Instantiate `RedditService`.
    * Configure the mock `reddit.subreddits.search` method to return a predefined list of mock subreddit objects when called with a specific topic.
    * Call `reddit_service.search_subreddits("test topic")`.
    * Assert that the mocked search method was called correctly and that the function returned the expected list of mock objects.

---

### Prompt 3: Subreddit Relevance Scoring

Next, I will implement the relevance scoring logic. This will be a separate utility function that uses the `RedditService`.

1. Create a new file: `app/utils/relevance.py`.
2. Create a corresponding test file: `tests/utils/test_relevance.py`.

3. In `app/utils/relevance.py`:
    * Define a function `score_and_rank_subreddits(subreddits: list, topic: str, reddit_service: 'RedditService') -> list`.
    * This function will iterate through the input list of subreddit objects.
    * For each subreddit, it will call a method on the `reddit_service` to fetch the top 25 "hot" posts. Let's name it `get_hot_posts(subreddit_name: str)`.
    * It will then calculate a `relevance_score` by counting how many of those 25 post titles contain the `topic` keyword (case-insensitive).
    * The function should return a sorted list of dictionaries, where each dictionary contains `name`, `description`, and `score`. The list should be sorted by `score` in descending order.

4. In `tests/utils/test_relevance.py`:
    * Write a test `test_score_and_rank_subreddits`.
    * Create mock subreddit objects (e.g., using `MagicMock`) with `display_name` attributes.
    * Create a mock `RedditService` instance.
    * Mock the `get_hot_posts` method on this service. For different subreddit names, make it return different lists of mock post objects with varying titles. For example, for `r/tech`, return 5 posts with "tech" in the title. For `r/gadgets`, return 3 posts with "tech" in the title.
    * Call `score_and_rank_subreddits` with your mock objects.
    * Assert that the returned list is sorted correctly and has the accurate scores (e.g., the entry for `r/tech` has a score of 5).

5. Now, add the `get_hot_posts(self, subreddit_name: str, limit: int = 25) -> list` method to `app/services/reddit_service.py` and write a corresponding unit test for it in `tests/services/test_reddit_service.py`, using mocks as before.

---

### Prompt 4: Reddit Service - Post Fetching & Filtering

I will now implement the logic for fetching and filtering posts from the chosen subreddit, as specified in FR-05 and FR-06. This is a critical and complex part of the `RedditService`.

1. In `app/services/reddit_service.py`, define a new method: `get_relevant_posts(self, subreddit_name: str) -> list`.

2. This method should perform the following steps:
    * Fetch the `top` posts from the last `day` (`time_filter='day'`).
    * Because the API returns posts sorted by score, not comments, you must fetch a generous number (e.g., 50) and then sort them in your application logic by the `num_comments` attribute in descending order.
    * Iterate through the sorted posts.
    * For each post, validate it according to FR-06. A post is valid if:
        * It is a text post (`post.is_self`).
        * OR it is a link post, but the `post.url` does not end with `.jpg`, `.jpeg`, `.png`, `.gif`, or `.mp4`. Also exclude common media domains like `i.redd.it`, `v.redd.it`, and `i.imgur.com`.
    * Add valid posts to a results list until you have found 5.
    * Return the list of 5 valid post objects.

3. In `tests/services/test_reddit_service.py`, write a new, comprehensive test `test_get_relevant_posts`.
    * Mock the `reddit.subreddit().top()` method to return a list of 20+ mock post objects.
    * The mock posts should be a mix of types:
        * Text posts (`is_self=True`).
        * Link posts to articles (e.g., `url='.../story.html'`).
        * Link posts to images (`url='.../image.jpg'`).
        * Link posts to media domains (`url='https://i.redd.it/xyz'`).
    * Give them different `num_comments` values, ensuring the correct sorting order is different from the initial list order.
    * Call `reddit_service.get_relevant_posts("testsub")`.
    * Assert that the returned list contains exactly 5 posts.
    * Assert that all returned posts are valid (not media links).
    * Assert that the list is sorted by `num_comments` in descending order.

---

### Prompt 5: Web Scraping Service

Now, create a service for scraping external article content (FR-07).

1. Create a new file: `app/services/scraper_service.py`.
2. Create a corresponding test file: `tests/services/test_scraper_service.py`.

3. In `app/services/scraper_service.py`:
    * Import `requests` and `BeautifulSoup`.
    * Define a function `scrape_article_text(url: str) -> str`.
    * Inside a `try...except` block to handle `requests.RequestException` and other potential errors:
        * Use `requests.get()` to fetch the URL content with a timeout.
        * Check `response.raise_for_status()`.
        * Use `BeautifulSoup` to parse the HTML.
        * Extract text from all `<p>` tags and join them together into a single string. This is a simple heuristic that works for many articles.
    * If scraping fails, return the specific string: `"Could not retrieve article content."` as per the spec.

4. In `tests/services/test_scraper_service.py`:
    * Write a test `test_scrape_article_success`.
    * Use `mocker.patch('requests.get')` to mock the `get` call.
    * Configure the mock response object to have a `status_code` of 200 and `text` containing a sample HTML string with several `<p>` tags.
    * Call `scrape_article_text` with a dummy URL.
    * Assert that the returned string is the concatenated text from the `<p>` tags only.
    * Write a second test, `test_scrape_article_failure`.
    * Configure the mock `requests.get` to raise a `requests.exceptions.RequestException`.
    * Call `scrape_article_text` and assert that it returns the exact error message: `"Could not retrieve article content."`.

---

### Prompt 6: AI Summarization Service

Create a service to handle AI summarization (FR-08, FR-09), abstracting the OpenAI API calls.

1. Create `app/services/summarizer_service.py` and `tests/services/test_summarizer_service.py`.

2. In `app/services/summarizer_service.py`:
    * Import `openai` and the config module.
    * Set the `openai.api_key` from the config.
    * Define a function `summarize_content(content: str, prompt_type: str) -> str`. The `prompt_type` will be either "post" or "comments".
    * Inside a `try...except` block:
        * Create a system prompt based on the `prompt_type`. For "post", it could be "Summarize the following article text concisely." For "comments", it could be "Summarize the following Reddit comments, capturing the overall community sentiment and key discussion points."
        * Make an API call to `openai.ChatCompletion.create` using the `gpt-3.5-turbo` model, the system prompt, and the user-provided `content`.
        * Extract and return the summary from the response.
    * If the API call fails, return the specific string: `"AI summary could not be generated."`.

3. In `tests/services/test_summarizer_service.py`:
    * Write a test `test_summarize_post_success`.
    * Use `mocker.patch('openai.ChatCompletion.create')` to mock the API call.
    * Configure the mock to return a predictable API response structure containing a sample summary.
    * Call `summarize_content("some long text", "post")`.
    * Assert that `openai.ChatCompletion.create` was called with the correct model and prompt structure.
    * Assert that the function returns the summary from the mock response.
    * Write a separate test `test_summarize_failure` where you configure the mock to raise an exception, and assert the function returns the correct error string.

---

### Prompt 7: Report Generation Module

Create the final module that assembles the collected data into a Markdown report (FR-10, FR-11).

1. Create `app/utils/report_generator.py` and `tests/utils/test_report_generator.py`.

2. In `app/utils/report_generator.py`, define a function `create_markdown_report(report_data: list, subreddit: str, topic: str) -> str`.
    * The `report_data` will be a list of dictionaries. Each dictionary will contain: `title`, `url`, `post_summary`, `comments_summary`.
    * The function should build a multi-line Markdown string.
    * The report should have a main header, e.g., `# Reddit Report: [Topic] in r/[Subreddit]`.
    * Then, for each item in `report_data`, create a section:

        ```markdown
        ---
        ### 1. [Post Title]
        **Link:** [Post URL]

        #### Post Summary
        [AI-generated post summary here]

        #### Community Sentiment Summary
        [AI-generated comments summary here]
        ```

    * Return the complete Markdown string.

3. In `tests/utils/test_report_generator.py`:
    * Write a test `test_create_markdown_report`.
    * Create a sample `report_data` list with 2-3 mock post entries.
    * Call `create_markdown_report` with this data.
    * Assert that the returned string contains key expected Markdown elements (`#`, `###`, `**Link:**`, etc.) and the data from your sample list.

---

### Prompt 8: FastAPI Scaffolding and Main Workflow

Now it's time to wire everything together using FastAPI. I'll create the API endpoints that orchestrate the entire workflow.

1. In `app/main.py`:
    * Import `FastAPI`, `StreamingResponse`, and all the services and utils we've created (`RedditService`, `score_and_rank_subreddits`, `get_relevant_posts`, `scrape_article_text`, `summarize_content`, `create_markdown_report`).
    * Instantiate FastAPI: `app = FastAPI()`.
    * Instantiate the `RedditService`.

2. Create the first endpoint for subreddit discovery (FR-04):
    * Define a GET endpoint `/discover-subreddits/{topic}`.
    * This endpoint should:
        * Call `reddit_service.search_subreddits(topic)`.
        * If no subreddits are found, return a JSON error.
        * Call `score_and_rank_subreddits` with the results.
        * Return the top 3 results as JSON.

3. Create the main report generation endpoint:
    * Define a GET endpoint `/generate-report/{subreddit}/{topic}`.
    * This endpoint will orchestrate the full process:
        a. Call `reddit_service.get_relevant_posts(subreddit)`. If none, return an error.
        b. Initialize an empty list `report_data`.
        c. Loop through the 5 valid posts:
            i. Get the post's title and URL.
            ii. If it's a text post, the content is `post.selftext`. If it's a link, call `scrape_article_text(post.url)`.
            iii. Call `summarize_content(content, "post")` to get the post summary.
            iv. Fetch the top 10 comments, concatenate their bodies, and call `summarize_content(comments_text, "comments")` to get the comments summary. (You will need to add a `get_top_comments` method to `RedditService` and test it).
            v. Append a dictionary with all this data to `report_data`.
        d. Call `create_markdown_report(report_data, subreddit, topic)`.
        e. Return the result as a downloadable file using `StreamingResponse`, setting the media type to `text/markdown` and the `Content-Disposition` header for download.

4. Add the `get_top_comments(self, post_id: str, limit: int = 15)` method to `RedditService` and its corresponding test.

5. (Conceptual) The integration tests for these endpoints would involve using FastAPI's `TestClient` and mocking the service-level functions (`search_subreddits`, `summarize_content`, etc.) to test the flow and logic within the endpoints themselves.

---

### Prompt 9: Dockerization

Finally, let's containerize the application for portability and deployment.

1. In the project's root directory, create a `Dockerfile`.
2. The `Dockerfile` should:
    * Start from an official Python 3.9 image (e.g., `python:3.9-slim`).
    * Set a working directory inside the container (e.g., `/app`).
    * Copy the `pyproject.toml` and `poetry.lock` (or `requirements.txt`) files into the container.
    * Install the dependencies using `pip install .` if using `pyproject.toml` with setuptools, or `pip install -r requirements.txt`. It's important to do this *before* copying the app code to leverage Docker's layer caching.
    * Copy the entire `app` directory into the container's working directory.
    * Expose the port the application will run on (e.g., 8000).
    * Define the command to run the application using `uvicorn`: `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`.

3. (Optional) Create a `docker-compose.yml` file to make it easier to run locally. It should define one service, `app`, build from the Dockerfile, map the container's port 8000 to the host's port 8000, and load environment variables from a local `.env` file.
