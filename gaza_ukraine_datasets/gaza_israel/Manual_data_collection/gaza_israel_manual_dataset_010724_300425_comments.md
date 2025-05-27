# Gaza-Israel dataset (manual data collection)

[Gaza_Israel_Dataset_Manual_Collection_010724-300425](Gaza-Israel%20dataset%20(manual%20data%20collection)%201db4118f8ead80b2aa75f8b2c8446622/Gaza_Israel_Dataset_Manual_Collection_010724-30042%201d14118f8ead80b5ba52cc506f5f863a.csv)

- Methodology (AFP Factcheck, Reuters):
    - Collecting all text-only or text & image claims (time frame: 07/24 - 04/25 (30.04.25))
    - not collecting video claims
    - not collecting samples which are not related to Gaza & Israel (e.g., Turkey speaks with Syria representatives)
        - but including samples which are related to Hezbollah & Lebanon, if they appear in the queries → but no explicit new queries with “Lebanon” or “Hezbollah”
    - not including duplicative fact checking samples (e.g., Reuters: “Gaza Fact Check”, “Israel Fact Check”)
- Snopes:
    - Queries: “Gaza”, “Israel”
    - Only taking fact-checking articles and not news articles (which often also contain claims, but no fact check)
        - e.g., https://www.snopes.com/news/2025/04/11/us-citizenship-israel-antisemitism/
    - Fact-Checking Label Explanations: https://www.snopes.com/fact-check-ratings/
- Politifact:
    - only fact checks with query “Israel”, no fact checks with query “Gaza”
    - not collecting samples which are not related to Gaza & Israel
        - e.g, Lebanon




## Claim_Date and Review_Date Columns (Date of Collection: 14.05.2025)


- Claim_Date:

  - The date that is mentioned in the fact-checking article

- Review_Date:
  - Either the published or updated date of the fact-checking article



