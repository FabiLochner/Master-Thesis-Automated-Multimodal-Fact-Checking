# Own Benchmark/Dataset

### Criteria:

- Topic: War in Gaza (political, high-stake, ongoing event)
- Timeline: After 08/24 (Knowledge Cutoff Gemini 2.0 Flash (Lite))
- Mediums:
    - Text-Only
    - Images
    - Videos
- Contributions/Focus:
    - AI-generated images
    - Photoshopped/manipulated/altered images
    - AI-generated videos
    - OOC images & videos

Possible queries to search fact-checking websites & for **Google FactCheck Claim Search API:**

- **Gaza (Fact Check)**
- **Westbank**
- **Palestine**
- **Israel**

[Overview Fact-Checking Websites](Own%20Benchmark%20Dataset%201ce4118f8ead808a96bbee54ed5faf33/Overview%20Fact-Checking%20Websites%201ce4118f8ead80138f24f824b677da7d.csv)

[X Premium Account, Video Downloads & Rules/Policies](https://www.notion.so/X-Premium-Account-Video-Downloads-Rules-Policies-1d04118f8ead80078253f1514902b90a?pvs=21)

![image.png](Own%20Benchmark%20Dataset%201ce4118f8ead808a96bbee54ed5faf33/image.png)

VERITE articles.csv:

| true_url (image) | false_caption | true_caption | false_url (image) | query | snopes/reuters url (article) |
| --- | --- | --- | --- | --- | --- |
| https://mediaproxy.snopes.com/width/600/https://media.snopes.com/2022/12/a_video_shot_in_china_showed_people_being_forcibly_dragged_to_covid_quarantine_in_2020_and_not_2022.jpg | Photograph shows Chinese officials in white protective hazmat suits carrying people down a hallway to be quarantined for having COVID-19 in November 2022. | Photograph shows a family that was taken away by local epidemic prevention personnel after they had returned home from Hubei Province in February 2020 while they were asked to self-quarantine in their homes for 14 days. | https://static.dw.com/image/63908432_604.jpg | shenzhen police arresting during covid | https://www.snopes.com/fact-check/china-covid-quarantine-video/ |

Snopes:

- false caption wording: A video recorded in November 2022 shows Chinese officials in white protective hazmat suits carrying people down a hallway to be quarantined for COVID-19.

VERITE.csv:

| caption | image_path | label |
| --- | --- | --- |
| Photograph shows a family that was taken away by local epidemic prevention personnel after they had returned home from Hubei Province in February 2020 while they were asked to self-quarantine in their homes for 14 days. | images/true_0.jpg | true |
| Photograph shows Chinese officials in white protective hazmat suits carrying people down a hallway to be quarantined for having COVID-19 in November 2022. | images/true_0.jpg | miscaptioned |
| Photograph shows a family that was taken away by local epidemic prevention personnel after they had returned home from Hubei Province in February 2020 while they were asked to self-quarantine in their homes for 14 days. | images/false_0.jpg | out-of-context |

[Overview Claims Text-Only & Images Fact-Checking Websites](Own%20Benchmark%20Dataset%201ce4118f8ead808a96bbee54ed5faf33/Overview%20Claims%20Text-Only%20&%20Images%20Fact-Checking%20W%201d14118f8ead80b5ba52cc506f5f863a.csv)

- Methodology (AFP Factcheck, Reuters):
    - Collecting all text-only or text & image claims (time frame: 07/24 - 04/25 (10.04.25))
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
    

[Overview Social Media Platforms & Videos](Own%20Benchmark%20Dataset%201ce4118f8ead808a96bbee54ed5faf33/Overview%20Social%20Media%20Platforms%20&%20Videos%201ce4118f8ead804d916edfab638fea92.csv)

- Perma.cc
    - [Perma.cc](http://perma.cc/) is a web archiving service for legal and academic citations founded by the Harvard Library Innovation Lab in 2013
    - https://en.wikipedia.org/wiki/Perma.cc
- [Mvau.lt](http://Mvau.lt) (https://mvau.lt/)
    - **MediaVault is a unique and unprecedented tool in the fight against social media misinformation**
    - Our cutting-edge system gathers manipulated images and videos shared around the world that have been analyzed by reputable fact-checking organizations. The MediaVault archive allows fact-checkers to maintain a vital portion of their work, and enables quicker research and identification of patterns used in misleading social media posts.
    - MediaVault is free for use by fact-checkers, journalists and others working to debunk misinformation shared online, but registration is required.
    - [https://reporterslab.org/2024/12/03/locking-up-misinfo-in-the-reporters-lab-vault/](https://reporterslab.org/2024/12/03/locking-up-misinfo-in-the-reporters-lab-vault/)
    - Since the Reporters Lab announced the new feature in late October, MediaVault has seen a significant boost in users, with more than 200 new sign-ups.
- AI-detection software Hive
    - https://hivemoderation.com/ai-generated-content-detection

[Overview API Video Access Social Media Platforms](https://www.notion.so/Overview-API-Video-Access-Social-Media-Platforms-1d54118f8ead80c2a1e5dd35d36c9d28?pvs=21)

[How were the other benchmarks created?](Own%20Benchmark%20Dataset%201ce4118f8ead808a96bbee54ed5faf33/How%20were%20the%20other%20benchmarks%20created%201d04118f8ead80658b47c5e18d2016eb.csv)