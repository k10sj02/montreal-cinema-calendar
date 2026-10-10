const calendarUrl = "https://k10sj02.github.io/montreal-cinema-calendar/montreal-cinema.ics";

async function copyCalendarLink(button) {
  try {
    await navigator.clipboard.writeText(calendarUrl);
    const original = button.textContent;
    button.textContent = "Copied!";
    window.setTimeout(() => { button.textContent = original; }, 1800);
  } catch {
    window.prompt("Copy this calendar subscription URL:", calendarUrl);
  }
}

document.querySelectorAll("#copy-link, #copy-link-bottom").forEach((button) => {
  button.addEventListener("click", () => copyCalendarLink(button));
});

fetch("montreal-cinema.json", { cache: "no-store" })
  .then((response) => {
    if (!response.ok) throw new Error("Schedule status unavailable");
    return response.json();
  })
  .then((data) => {
    const count = new Intl.NumberFormat("en-CA").format(data.count);
    const updated = new Intl.DateTimeFormat("en-CA", {
      month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
      timeZone: "America/Toronto", timeZoneName: "short"
    }).format(new Date(data.generated));
    document.querySelector("#calendar-status").textContent = `${count} screenings · Updated ${updated}`;
  })
  .catch(() => {
    document.querySelector("#calendar-status").textContent = "Calendar updates automatically every six hours";
  });
