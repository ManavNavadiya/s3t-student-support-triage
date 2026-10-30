"""Use the asset from your own Python code.   python examples/use_as_a_module.py"""
from s3t import Triage

triage = Triage()                      # loads the model once (hybrid if available)
print("Model:", triage.info()["model"], "| thresholds:", triage.info()["review_thresholds"])

result = triage.predict("Hi, I can't log in to Canvas and my STAT 230 quiz closes today.",
                        id="ticket-001")
print(result.category.label, result.category.confidence)
print(result.urgency.label, result.urgency.confidence, result.confidence_band)
print("Human review needed:", result.human_review.required, result.human_review.reasons)
print("Extracted:", result.entities.model_dump(), result.emotions)

# Batch: faster than a loop (one encoder pass for all messages)
inbox = ["My financial aid has not arrived.", "How do I get my transcript?",
         "I feel hopeless and can't cope anymore."]
for r in triage.predict_batch(inbox):
    flag = "REVIEW" if r.human_review.required else "auto"
    print(f"[{flag}] {r.category.label:28} {r.category.confidence:.2f}  {r.recommended_action}")

# Plain dict / JSON for another system
payload = result.model_dump()
