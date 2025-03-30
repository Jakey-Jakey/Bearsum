# pocketflow_logic/utils/github_utils.py
import requests
import logging
from urllib.parse import urlparse
import re
from datetime import datetime, timedelta, timezone
import base64 # <<< ADDED IMPORT

log = logging.getLogger(__name__)

# Define custom exceptions for specific errors
class GitHubUrlError(ValueError):
    """Custom exception for invalid GitHub URLs."""
    pass

class RepoNotFoundError(Exception):
    """Custom exception for 404 errors from GitHub API (repo level)."""
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


# <<< NEW FUNCTION START >>>
def get_readme_content(owner: str, repo: str) -> str | None:
    """
    Fetches and decodes the README content for a public GitHub repository.

    Args:
        owner: The repository owner's username.
        repo: The repository name.

    Returns:
        The decoded README content as a string, or None if not found or an error occurs.
    Raises:
        GitHubApiError: For API errors other than 404 (rate limit, server error, connection issues).
                       Allows the caller to distinguish between 'not found' and 'fetch failed'.
    """
    if not owner or not repo:
        log.warning("get_readme_content called with empty owner or repo.")
        return None # Or raise ValueError, but None aligns with graceful degradation

    api_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/readme"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    log.info(f"Fetching README for {owner}/{repo}...")

    try:
        response = requests.get(api_url, headers=headers, timeout=REQUEST_TIMEOUT)

        # Handle status codes
        if response.status_code == 200:
            readme_data = response.json()
            if not isinstance(readme_data, dict) or 'content' not in readme_data:
                log.error(f"Unexpected API response format for {owner}/{repo} README: {readme_data}")
                # Treat unexpected format as an error, but return None for simplicity
                # raise GitHubApiError("Unexpected data format for README from GitHub API.")
                return None # Graceful degradation if format is wrong

            encoded_content = readme_data.get('content')
            encoding = readme_data.get('encoding')

            if encoding != 'base64' or not encoded_content:
                log.warning(f"README for {owner}/{repo} has unexpected encoding ('{encoding}') or is empty.")
                return None # Cannot decode if not base64 or empty

            try:
                # Add padding if necessary for base64 decoding
                encoded_content += '=' * (-len(encoded_content) % 4)
                decoded_bytes = base64.b64decode(encoded_content)
                readme_content = decoded_bytes.decode('utf-8')
                log.info(f"Successfully fetched and decoded README for {owner}/{repo} ({len(readme_content)} chars).")
                return readme_content
            except (base64.binascii.Error, UnicodeDecodeError) as decode_err:
                log.error(f"Error decoding README content for {owner}/{repo}: {decode_err}")
                return None # Treat decoding errors gracefully

        elif response.status_code == 404:
            log.info(f"README not found for {owner}/{repo} (404).")
            return None # Explicitly return None for 'Not Found'
        elif response.status_code == 403:
            log.warning(f"Access forbidden or rate limit exceeded for {owner}/{repo} README (403).")
            raise GitHubApiError("Access forbidden or GitHub API rate limit exceeded fetching README.")
        else:
            # Handle other 4xx/5xx errors
            log.error(f"GitHub API error fetching README for {owner}/{repo}: {response.status_code} - {response.text[:200]}")
            raise GitHubApiError(f"GitHub API returned status {response.status_code} fetching README.")

    except requests.exceptions.Timeout:
        log.error(f"Request timed out while fetching README for {owner}/{repo}.")
        raise GitHubApiError("Request to GitHub API timed out fetching README.")
    except requests.exceptions.RequestException as e:
        log.error(f"Network error fetching README for {owner}/{repo}: {e}", exc_info=True)
        raise GitHubApiError(f"Could not connect to GitHub API fetching README: {e}")
    except Exception as e:
        # Catch-all for unexpected errors during processing
        log.error(f"Unexpected error fetching README for {owner}/{repo}: {e}", exc_info=True)
        # Return None to allow proceeding with commits if possible
        # raise GitHubApiError("An unexpected error occurred while fetching the README.")
        return None # Graceful degradation on unexpected errors
# <<< NEW FUNCTION END >>>


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
                 log.error(f"Unexpected API response format for {owner}/{repo} commits: {type(commits_data)}")
                 raise GitHubApiError("Unexpected data format for commits from GitHub API.")

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
             log.warning(f"Access forbidden or rate limit exceeded for {owner}/{repo} commits (403). Response: {response.text[:200]}")
             raise GitHubApiError("Access forbidden or GitHub API rate limit exceeded fetching commits. Please wait and try again.")
        elif response.status_code == 422:
             log.warning(f"Unprocessable Entity (e.g., empty repo) for {owner}/{repo} commits (422).")
             # Treat as no commits found
             return []
        else:
            # Handle other 4xx/5xx errors
            log.error(f"GitHub API error fetching commits for {owner}/{repo}: {response.status_code} - {response.text[:200]}")
            raise GitHubApiError(f"GitHub API returned status {response.status_code} fetching commits.")

    except requests.exceptions.Timeout:
        log.error(f"Request timed out while fetching commits for {owner}/{repo}.")
        raise GitHubApiError("Request to GitHub API timed out fetching commits.")
    except requests.exceptions.RequestException as e:
        log.error(f"Network error fetching commits for {owner}/{repo}: {e}", exc_info=True)
        raise GitHubApiError(f"Could not connect to GitHub API fetching commits: {e}")
    except Exception as e:
        # Catch-all for unexpected errors during processing
        log.error(f"Unexpected error fetching commits for {owner}/{repo}: {e}", exc_info=True)
        raise GitHubApiError("An unexpected error occurred while fetching commits.")
