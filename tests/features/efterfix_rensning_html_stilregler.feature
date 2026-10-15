Feature: Enkla regler i <style> som gömmer text tolkas
  Som användare av en LLM som läser min e-post
  vill jag att text som en klassregel i mejlets <style> gömmer inte heller når modellen
  så att en avsändare inte kan gömma instruktioner med .x{display:none}.

  Scenario: En klassregel med display:none gömmer elementet
    Given ett HTML-mejl med innehållet '<style>.pre{display:none !important}</style><p>Hej</p><div class="pre">SECRET</div>'
    When jag hämtar mejlet som text med get_email
    Then ska brödtexten vara "Hej"

  Scenario: En regel inuti @media tolkas inte
    Given ett HTML-mejl med innehållet '<style>@media (max-width:600px){.m{display:none}}</style><p class="m">Hej</p>'
    When jag hämtar mejlet som text med get_email
    Then ska brödtexten vara "Hej"
