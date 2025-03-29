# pocketflow_logic/utils/github_utils.py
import requests
import logging
from urllib.parse import urlparse
import re
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

# Define custom exceptions for specific errors
class GitHubUrlError(ValueError):
    """Custom exception for invalid GitHub URLs."""
    pass

class RepoNotFoundError(Exception):
    """Custom exception for 404 errors from GitHub API."""
    pass

class GitHubApiError(Exception):
    """Custom exception for general GitHub API errors (rate limits, server issues)."""
    pass


# Regex for valid owner/repo names (simple version)
VALID_NAME_REGEX = re.compile(r"^[a-zA-Z0-9._-]+$")
GITHUB_API_BASE = "https://api.github.com"
REQUEST_TIMEOUT = 15 # seconds

def parse_github_url(url: str) -> tuple[str | None, str | None]:
    """
    Parses a GitHub repository URL and extracts owner and repo name.

    Args:
        url: The URL string to parse.

    Returns:
        A tuple (owner, repo) if valid, otherwise raises GitHubUrlError.
    """
    if not url:
        raise GitHubUrlError("URL cannot be empty.")

    try:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
            raise GitHubUrlError("URL must be a valid HTTPS GitHub URL (github.com).")

        path_parts = [part for part in parsed.path.strip('/').split('/') if part]

        # Handle common variations like trailing .git or extra paths
        if len(path_parts) >= 2:
            owner = path_parts[0]
            repo = path_parts[1]
            # Remove potential .git suffix
            if repo.lower().endswith('.git'):
                repo = repo[:-4]

            if VALID_NAME_REGEX.match(owner) and VALID_NAME_REGEX.match(repo):
                log.info(f"Parsed GitHub URL: owner='{owner}', repo='{repo}'")
                return owner, repo
            else:
                raise GitHubUrlError("Invalid characters in owner or repository name.")
        else:
            raise GitHubUrlError("URL path does not contain valid owner/repository structure.")

    except ValueError as e: # Catch potential errors during parsing itself
        raise GitHubUrlError(f"Could not parse URL: {e}")
    except Exception as e: # Catch unexpected errors
        log.error(f"Unexpected error parsing URL '{url}': {e}", exc_info=True)
        raise GitHubUrlError("An unexpected error occurred while parsing the URL.")


def get_recent_commits(owner: str, repo: str, days=3, limit=30) -> list[dict]:
    """
    Fetches recent commits for a public GitHub repository.

    Args:
        owner: The repository owner's username.
        repo: The repository name.
        days: Fetch commits from the last N days.
        limit: Maximum number of commits to return.

    Returns:
        A list of commit details dictionaries.
    Raises:
        RepoNotFoundError: If the repository is not found (404).
        GitHubApiError: For other API errors (rate limit, server error, connection issues).
    """
    if not owner or not repo:
        raise ValueError("Owner and repo cannot be empty.")

    api_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits"

    # Calculate the 'since' date for filtering
    since_date = datetime.now(timezone.utc) - timedelta(days=days)
    params = {
        "per_page": min(limit, 100), # API max is 100
        "since": since_date.isoformat()
    }

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28" # Recommended practice
    }

    log.info(f"Fetching commits for {owner}/{repo} since {since_date.isoformat()} (limit {limit})...")

    try:
        response = requests.get(api_url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)

        # Check status code FIRST
        if response.status_code == 200:
            commits_data = response.json()
            if not isinstance(commits_data, list):
                 log.error(f"Unexpected API response format for {owner}/{repo}: {type(commits_data)}")
                 raise GitHubApiError("Unexpected data format from GitHub API.")

            extracted_commits = []
            for commit_info in commits_data[:limit]: # Apply limit again just in case API returns more
                try:
                    commit_details = commit_info.get('commit', {})
                    author_details = commit_details.get('author', {})
                    # Prefer commit author name, fallback to GitHub login if available
                    author_name = author_details.get('name', 'Unknown Author')
                    if author_name == 'Unknown Author' and commit_info.get('author'):
                        author_name = commit_info['author'].get('login', 'Unknown Author')

                    commit_date = author_details.get('date', 'Unknown Date')
                    # Keep only the first line of the commit message
                    commit_message = commit_details.get('message', '').split('\n', 1)[0].strip()

                    extracted_commits.append({
                        'author': author_name,
                        'date': commit_date,
                        'message': commit_message
                    })
                except (TypeError, KeyError, AttributeError) as e:
                    log.warning(f"Could not parse commit info for {owner}/{repo}: {e} - Commit: {commit_info.get('sha', 'N/A')}")
                    # Skip this commit if parsing fails

            log.info(f"Successfully fetched {len(extracted_commits)} commits for {owner}/{repo}.")
            return extracted_commits

        elif response.status_code == 404:
            log.warning(f"Repository {owner}/{repo} not found (404).")
            raise RepoNotFoundError(f"Repository '{owner}/{repo}' not found or is private.")
        elif response.status_code == 403:
             log.warning(f"Access forbidden or rate limit exceeded for {owner}/{repo} (403). Response: {response.text[:200]}")
             # Check headers for rate limit info if needed
             # remaining = response.headers.get('X-RateLimit-Remaining')
             raise GitHubApiError("Access forbidden or GitHub API rate limit exceeded. Please wait and try again.")
        elif response.status_code == 422:
             log.warning(f"Unprocessable Entity (e.g., empty repo) for {owner}/{repo} (422).")
             # Treat as no commits found
             return []
        else:
            # Handle other 4xx/5xx errors
            log.error(f"GitHub API error for {owner}/{repo}: {response.status_code} - {response.text[:200]}")
            raise GitHubApiError(f"GitHub API returned status {response.status_code}.")

    except requests.exceptions.Timeout:
        log.error(f"Request timed out while fetching commits for {owner}/{repo}.")
        raise GitHubApiError("Request to GitHub API timed out.")
    except requests.exceptions.RequestException as e:
        log.error(f"Network error fetching commits for {owner}/{repo}: {e}", exc_info=True)
        raise GitHubApiError(f"Could not connect to GitHub API: {e}")
    except Exception as e:
        # Catch-all for unexpected errors during processing
        log.error(f"Unexpected error fetching commits for {owner}/{repo}: {e}", exc_info=True)
        raise GitHubApiError("An unexpected error occurred while fetching commits.")
