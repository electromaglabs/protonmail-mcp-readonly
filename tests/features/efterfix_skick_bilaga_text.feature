Feature: En textbilaga som läses direkt är rensad och märkt som opålitlig
  Som användare som låter en LLM läsa bilagor
  vill jag att en textbilaga inte för in osynliga instruktioner till modellen
  och att svaret säger att innehållet kommer från avsändaren.
  ([U+XXXX] står för det osynliga tecknet med den kodpunkten.)

  Scenario: Taggtecken och bidi-styrtecken tas bort ur en textbilaga
    Given ett mejl med textbilagan "notes.txt" med innehållet "Hej[U+E0049][U+E0047][U+E004E] v[U+202E]ärlden"
    When LLM:en läser bilaga 0 direkt
    Then ska innehållet vara "Hej världen"
    And ska svaret ha untrusted_content_notice
    And ska sanitized ange att 4 tecken togs bort ur innehållet

  Scenario: En ren textbilaga är oförändrad men ändå märkt
    Given ett mejl med textbilagan "notes.txt" med innehållet "Mötet flyttas till kl. 14."
    When LLM:en läser bilaga 0 direkt
    Then ska innehållet vara "Mötet flyttas till kl. 14."
    And ska svaret ha untrusted_content_notice
    And ska sanitized vara tom

  Scenario: Filnamnet i svaret är rensat
    Given ett mejl med textbilagan "faktura[U+202E]fdp.txt" med innehållet "x"
    When LLM:en läser bilaga 0 direkt
    Then ska filnamnet i svaret vara "fakturafdp.txt"
