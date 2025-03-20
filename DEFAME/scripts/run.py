"""Minimal running example for a multimodal fact-check."""

from defame.fact_checker import FactChecker
from defame.common import Image


fact_checker = FactChecker(llm="gpt_4o_mini")
#claim = ["According to the image",
 #        Image("in/example/statistics/coffee_exporters_2024.webp"),
  #       "Brazil was the global leading coffee exporting country in 2024 with 12.000 million U.S dollars."]

claim = ["The image",
         Image("in/example/sahara.webp"),
         "shows the Sahara in 2023 covered with snow!"]
#claim = ["Israel rejected a Hamas offer to free an American-Israeli captive in March 2025."]
report, _ = fact_checker.verify_claim(claim)
report.save_to("out/fact-check")
