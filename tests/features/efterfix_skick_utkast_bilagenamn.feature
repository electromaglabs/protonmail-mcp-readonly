Feature: update_draft visar rensade namn på bilagorna som följer med
  Som användare som låter en LLM ändra ett vidarebefordringsutkast
  vill jag att bilagenamnen i svaret är rensade från osynliga tecken
  så att ett namn som "faktura<RLO>fdp.exe" inte vilseleder modellen,
  medan själva bilagan följer med oförändrad.
  ([U+XXXX] står för det osynliga tecknet med den kodpunkten.)

  Scenario: Bilagenamn med bidi- och taggtecken rensas i kept_attachments
    Given ett utkast i Drafts med bilagan "faktura[U+202E]fdp.exe[U+E0049][U+E0047]"
    When LLM:en ersätter utkastet med update_draft
    Then ska kept_attachments vara "fakturafdp.exe"
    And ska bilagan i det nya utkastet ha kvar sitt ursprungliga namn
