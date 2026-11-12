const aiForm = document.querySelector("#ai-form");
const aiQuestion = document.querySelector("#ai-question");
const aiStatus = document.querySelector("#ai-status");
const aiAnswer = document.querySelector("#ai-answer");
const aiMatches = document.querySelector("#ai-matches");

if (aiForm) {
  aiForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    aiStatus.textContent = "Searching the provider directory and preparing suggestions…";
    aiAnswer.hidden = true;
    aiMatches.replaceChildren();

    try {
      const response = await fetch("/api/ai/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: aiQuestion.value.trim() }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "The assistant could not complete your request.");
      }

      aiAnswer.textContent = data.answer;
      aiAnswer.hidden = false;
      aiStatus.textContent = "Suggestions are based on the current provider directory.";
      if (data.matches?.length) {
        const heading = document.createElement("h3");
        heading.textContent = "Potential matches";
        aiMatches.append(heading);
        for (const match of data.matches) {
          const card = document.createElement("article");
          card.className = "ai-match-card";
          const name = document.createElement("strong");
          name.textContent = match.name;
          const details = document.createElement("p");
          details.textContent = `${match.category} · ${match.area}`;
          card.append(name, details);
          aiMatches.append(card);
        }
      }
    } catch (error) {
      aiStatus.textContent = error.message;
    }
  });
}
