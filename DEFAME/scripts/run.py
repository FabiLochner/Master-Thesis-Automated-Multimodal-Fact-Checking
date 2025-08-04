"""Minimal running example for a multimodal fact-check."""

from defame.fact_checker import FactChecker
from defame.common import Image

# added by me to test out whether Reverse Image Search can also be used with run.py
from defame.tools import WebSearch, ImageSearch, ReverseSearch, Geolocate
# fact_checker = FactChecker(
#     llm="gpt_4o_mini",
#     available_actions=[WebSearch, ImageSearch, ReverseSearch, Geolocate],
#     extra_plan_rules="Prioritize using image-based verification methods like image_search and reverse_search."
# )

fact_checker = FactChecker(llm="gemini-2.0-flash-lite",
                           available_actions=[WebSearch, ImageSearch, ReverseSearch, Geolocate],
                           extra_plan_rules= "Prioritize using image-based verification methods like image_search and reverse_search.")
#claim = ["The International Court of Justice (ICJ) ruled that Israel is an illegal state in July 2024."]

#claim = ["In November 2024, rock band U2 and singer Bob Geldof announced a multi-stadium tour to aid the Israeli army."]

claim = ["This image", Image("in/example/myanmar-earthquake.jpeg"),
         "shows the devastation of the 7.9-magnitude earthquake in Myanmar on March 28, 2025."]




#claim = ["The population in Gaza has increased by 2.02 percent since Oct. 7, 2023"]
#claim = ["تُظهِر الصورة ",Image ("in/example/gaza_prayer.webp"), "المسلمين وهم يصلون في غزة المدمرة في عيد الفطر عام 2025."]
#claim = ["Israel rejected a Hamas offer to free an American-Israeli captive in March 2025."]
#claim = ["На изображении", Image("in/example/ukraine_car_drone.webp"), "показан автомобиль, уничтоженный украинским беспилотником, в центре Санкт-Петербурга, Россия, 29 марта 2025 года."]

# claim = ["Israel rejected a Hamas offer to free an American-Israeli captive in March 2025."]

#claim =  ["The United Nations said in early 2024 there was no famine in Gaza."]
#claim = ["The U.S. government spent $50 million on condoms for Gaza, which Hamas is now using to manufacture bombs."]
report, _ = fact_checker.verify_claim(claim)
report.save_to("out/fact-check-myanmar-earthquake-2")

