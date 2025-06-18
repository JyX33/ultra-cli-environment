# Developer Specification: AI Reddit News Agent

**Version:** 1.0
**Date:** June 7, 2025

---

## 1. Project Overview

This document outlines the technical specifications for the "AI Reddit News Agent." The system's primary objective is to automate the process of finding relevant discussions on Reddit for a given topic and generating a concise, digestible report. The end-user provides a topic, and the system delivers a downloadable Markdown file summarizing the top, most engaging, and recent text-based posts from the most suitable subreddit.

---

## 2. Functional Requirements

* **FR-01: Topic Input:** The system must provide an interface for the user to input a text-based topic.
* **FR-02: Subreddit Discovery:** The system must programmatically search Reddit for subreddits whose names or descriptions match the input topic.
* **FR-03: Subreddit Relevance Scoring:** The system must analyze the discovered subreddits to determine their relevance to the topic by scanning their recent posts for mentions of the topic keywords.
* **FR-04: User-Driven Subreddit Selection:** The system must present the top 3 most relevant subreddits to the user and allow them to select one for the report.
* **FR-05: Post Identification:** Within the selected subreddit, the system must identify the top 5 posts from the last 24 hours, sorted in descending order by comment count.
* **FR-06: Content Type Filtering:** The system must validate that the selected posts are either text-based or link to an external article. Posts that are direct links to media (e.g., `.jpg`, `.png`, `.gif`, `.mp4`) must be skipped, and the next valid post in the sorted list should be taken.
* **FR-07: External Content Extraction:** For posts linking to an external article, the system must be able to scrape the main text content of that article.
* **FR-08: AI-Powered Content Summarization:** The system must generate an AI summary of the post's text content or the scraped article content.
* **FR-09: AI-Powered Discussion Summarization:** The system must generate a separate AI summary of the top-voted comments for each post to capture community sentiment.
* **FR-10: Report Generation:** The system must compile the collected data into a single, structured report.
* **FR-11: Markdown Output:** The final report must be formatted in Markdown (`.md`) and made available to the user as a downloadable file.

---

## 3. System Architecture & Technology Stack

A modular backend-driven architecture is recommended. A simple frontend can handle user input and display results, while a robust backend orchestrates the data gathering and processing.

* **Backend:** **Python 3.9+**
  * **Reddit API Interaction:** `PRAW` (Python Reddit API Wrapper) for authenticated access to the Reddit API.
  * **Web Scraping:** `Requests` to fetch article HTML and `BeautifulSoup4` or `Scrapy` to parse and extract text content.
  * **AI/NLP:** A pre-trained abstractive summarization model. Recommended to use an API service for simplicity and power.
    * **Option A:** Hugging Face API (e.g., `facebook/bart-large-cnn` model).
    * **Option B:** OpenAI API (using `gpt-3.5-turbo` or `gpt-4` with a summarization prompt).
    * **Option C:** Google Gemini API.
  * **Web Framework (Optional but recommended):** `Flask` or `FastAPI` to serve the frontend and handle API requests between the client and backend.

* **Frontend:** **HTML5, CSS3, JavaScript**
  * A simple single-page interface with a text input field, a "Generate" button, a loading indicator, a section to display the subreddit choices, and a final download link for the report.
  * JavaScript's `fetch` API will be used to communicate with the backend.

* **Environment:**
  * All API keys (Reddit, NLP Provider) must be stored as environment variables (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `NLP_API_KEY`, etc.) and not hardcoded.
  * The application should be containerized using **Docker** for portability and ease of deployment.

---

## 4. Data Handling & Workflow Logic

This section details the step-by-step data processing flow.

1. **Input:** User submits a `topic` (string) via the frontend.
2. **Subreddit Search (Backend):**
    * Use the Reddit API to search for subreddits matching the `topic`. (e.g., `reddit.subreddits.search(topic)`).
    * Limit initial results to a reasonable number (e.g., 10 candidates).
3. **Relevance Scoring (Backend):**
    * For each candidate subreddit, fetch the top 25 posts from the "Hot" category.
    * Iterate through the titles of these 25 posts. The **relevance score** is the number of posts whose titles contain the `topic` keyword(s).
    * Rank the candidate subreddits by this score in descending order.
    * Return the names and descriptions of the top 3 subreddits to the frontend.
4. **User Selection (Frontend/Backend):**
    * Frontend displays the 3 choices. User clicks one.
    * Frontend sends the `chosen_subreddit` back to the backend.
5. **Post Selection (Backend):**
    * Access the chosen subreddit (e.g., `reddit.subreddit(chosen_subreddit)`).
    * Fetch posts using the `top` filter with a time filter of `day` (last 24 hours).
    * In the application logic, sort these posts by `num_comments` (descending).
    * Initialize an empty list, `valid_posts`.
    * Iterate through the sorted posts. For each post:
        * Check if the post is self-text (`is_self`) or a link to a non-media domain. Skip if it links directly to an image/video file or common media hosts (e.g., `i.imgur.com`, `v.redd.it`).
        * If valid, add the post object to `valid_posts`.
        * Stop when `len(valid_posts) == 5`.
6. **Content Processing (Backend):**
    * For each of the 5 `valid_posts`:
        * **Content Extraction:**
            * If it's a text post, the content is `post.selftext`.
            * If it's a link post, use the scraping library to fetch and parse the text from `post.url`.
        * **Comment Extraction:**
            * Fetch the post's comments, sorted by `top`.
            * Concatenate the body of the top 10-15 comments into a single string.
        * **AI Summarization:**
            * Make two API calls to the chosen NLP service:
                1. To summarize the extracted post/article content.
                2. To summarize the concatenated comment string.
7. **Output Generation (Backend):**
    * Assemble a single Markdown string using a template literal, populating it with the post titles, URLs, and the two AI-generated summaries for each of the 5 posts.
    * Create an API endpoint (e.g., `/report`) that, when called, returns this Markdown string with the appropriate headers for file download (`Content-Disposition: attachment; filename="report.md"`).

---

## 5. Error Handling Strategies

The system must be resilient to common failures.

* **API Rate Limits:** Implement exponential backoff or use `PRAW`'s built-in automatic rate limit handling.
* **No Subreddits Found:** If the initial search returns zero results, the backend should return a specific error message (e.g., `{"error": "No subreddits found"}`) which the frontend displays to the user.
* **No Posts Found:** If the `valid_posts` list has a length of 0 after checking, return a similar error (`{"error": "No relevant posts found in this subreddit"}`).
* **Web Scraping Failures:** Wrap scraping calls in a `try...except` block. Handle common exceptions like `ConnectionError`, `Timeout`, and HTTP status codes (403, 404, 503). If a scrape fails, the "Content Summary" for that post should be: `"Could not retrieve article content."`
* **Summarization API Failures:** If the NLP API call fails, the corresponding summary should be: `"AI summary could not be generated."`
* **Invalid Input:** The backend should validate the input `topic` to ensure it's not empty or excessively long.

---

## 6. Testing Plan

A thorough testing plan is required to ensure reliability.

* **Unit Tests:**
  * Test individual functions in isolation.
  * `test_relevance_scoring()`: Mock the Reddit API and provide a known set of posts to a candidate subreddit. Assert that the correct score is calculated.
  * `test_content_extraction()`: Test the scraping function with a saved local HTML file to see if it correctly extracts the main text.
  * `test_summarization()`: Mock the NLP API. Test that the function correctly formats text and handles successful/failed API responses.
  * `test_media_post_skipping()`: Create mock post objects with various media URLs and assert that the filtering logic correctly skips them.

* **Integration Tests:**
  * Test the interaction between modules.
  * Test the full flow from subreddit search to relevance scoring, ensuring the top 3 are correctly identified based on the scoring logic.
  * Test the flow from post selection to content processing, ensuring valid posts are correctly passed to the summarization module.

* **End-to-End (E2E) Test Cases:**
  * **Happy Path:** Use a common topic like `"NVIDIA"` or `"machine learning"` that is guaranteed to produce results. Verify a valid Markdown file is generated with 5 entries.
  * **Niche Topic:** Use a niche topic like `"permaculture design"` or `"FPV drones"`. Verify the system finds specific, relevant subreddits.
  * **No Posts Edge Case:** Manually select a valid but low-activity subreddit and run the agent for a topic unlikely to have been discussed in 24 hours. Verify the "No relevant posts found" error is correctly triggered.
  * **No Subreddits Edge Case:** Use a nonsensical topic like `"asdfghjkl"`. Verify the "No subreddits found" error is shown.
  * **Media-Heavy Subreddit:** Run the agent on a topic whose primary subreddit is image-based (e.g., topic: `"astrophotography"`, subreddit: `r/astrophotography`). Verify the agent correctly skips media posts and either finds 5 text posts or gracefully reports that it cannot.
