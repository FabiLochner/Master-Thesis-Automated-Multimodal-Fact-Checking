import requests
import json
from datetime import datetime
from config.globals import api_keys
from defame.tools.search.remote_search_api import scrape

# Google Fact Check API endpoint
FACT_CHECK_API_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"

# Replace this with your actual API key
#API_KEY = api_keys["google_api_key"] 
API_KEY = api_keys["google_fact_check_tools_api_key"]

def fetch_recent_claims(query=None, max_age_days=None, page_token=None, language_code=None):
    """
    Fetch claims from Google Fact Check API based on a query or maxAgeDays.
    """
    params = {
        "key": API_KEY,
    }
    if query:
        params["query"] = query
    if max_age_days:
        params["maxAgeDays"] = max_age_days
    if page_token:
        params["pageToken"] = page_token
    if language_code:
        params["languageCode"] = language_code #adding language code filter

    response = requests.get(FACT_CHECK_API_URL, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code}, {response.text}")
        return None

def scrape_claims_after_date(after_date, query=None, language_code=None): #added language_code to only get English claims
    """
    Scrape claims made after a specific date.
    """
    days_since = (datetime.utcnow() - datetime.fromisoformat(after_date.rstrip("Z"))).days
    all_claims = []
    next_page_token = None

    while True:
        data = fetch_recent_claims(query=query, max_age_days=days_since, page_token=next_page_token, language_code=language_code)
        if not data or "claims" not in data:
            break

        all_claims.extend(data["claims"])
        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

    return all_claims



# # Add function to scrape claims with start and end date that is before current date (e.g., 010724-300425)
# def scrape_claims_between_dates(after_date, end_date, query=None, language_code = None): #added end_date here
#     """ 
#     Scrape claims between start and end date.
#     """
#     end_date_object = datetime.fromisoformat(end_date.rstrip("Z")) 

#     days_since = (end_date_object - datetime.fromisoformat(after_date.rstrip("Z"))).days
#     all_claims = []
#     next_page_token = None

#     while True:
#         data = fetch_recent_claims(query=query, max_age_days=days_since, page_token=next_page_token, language_code=language_code)
#         if not data or "claims" not in data:
#             break

#         all_claims.extend(data["claims"])
#         next_page_token = data.get("nextPageToken")
#         if not next_page_token:
#             break

#     return all_claims



def identify_claims_with_images(claims):
    """
    Identify claims with associated images in the claimReview.
    """
    for claim in claims:
        claim["hasImages"] = False  # Default assumption
        if "claimReview" in claim:
            for review in claim["claimReview"]:
                if review.get("url"):
                    scraped = scrape(review["url"])
                    if scraped.has_images():
                        claim["hasImages"] = True
                        claim["imageReferences"] = scraped.images
                        scraped.images
                    break
    return claims

def save_claims_to_json(claims, query, after_date, language_code, filename="claims.json"):
    """
    Save claims to a JSON file with query and after_date metadata.
    """
    output_data = {
        "query": query,
        "after_date": after_date, 
        "language_code": language_code,
        "claims": claims
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=4, ensure_ascii=False)
    print(f"Saved {len(claims)} claims to {filename}")

def main():
    # Define the query and after date
    after_date = "2024-07-01T00:00:00Z"  # July 1, 2024
    #end_date = "2025-04-30T23:59:59Z" # April 30, 2025
    query = "Russia"  # ukraine, russia, putin, israel, israel defence force, hamas, taiwan, gaza
    language_code = "en" #adding language code

    print(f"Fetching claims after {after_date}...")
    claims = scrape_claims_after_date(after_date=after_date, query=query, language_code=language_code)

    # Identify claims with images
    #claims_with_metadata = identify_claims_with_images(claims)

    # Save to JSON file
    save_claims_to_json(claims, query, after_date, language_code, filename="claims.json") #added end_date and language_code

    print(f"Found {len(claims)} claims. Saved with metadata to 'claims_with_images.json'.")

if __name__ == "__main__":
    main()
