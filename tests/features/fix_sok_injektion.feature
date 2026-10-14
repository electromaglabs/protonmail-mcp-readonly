Feature: Sökvärden kan inte smuggla in egna IMAP-kommandon
  Som användare av ett läsverktyg
  vill jag att ett sökvärde aldrig kan bli ett eget IMAP-kommando
  så att en prompt-injektion i ett mejl inte kan radera eller ändra min post.

  Scenario: Radbrytning i ämnet avvisas innan något skickas
    Given att jag är ansluten till en brevlåda
    When jag söker med subject "x\r\nZZ1 EXPUNGE"
    Then ska sökningen avvisas med ett fel som nämner "subject"
    And ska inget kommando ha skickats till servern

  Scenario: Radbrytning i avsändaren avvisas innan något skickas
    Given att jag är ansluten till en brevlåda
    When jag söker med from_addr "a@b.se\nZZ1 DELETE INBOX"
    Then ska sökningen avvisas med ett fel som nämner "from_addr"
    And ska inget kommando ha skickats till servern

  Scenario: Ett datum med ett påhängt kommando avvisas
    Given att jag är ansluten till en brevlåda
    When jag söker med since "01-Jan-2020\r\nZZ3 UID STORE 1:* +FLAGS (\Deleted)"
    Then ska sökningen avvisas med ett fel som nämner "since"
    And ska inget kommando ha skickats till servern

  Scenario: Ett datum i okänt format avvisas i stället för att ge tomt svar
    Given att jag är ansluten till en brevlåda
    When jag söker med before "2024/01/05"
    Then ska sökningen avvisas med ett fel som nämner "YYYY-MM-DD"
    And ska inget kommando ha skickats till servern

  Scenario: Ett ISO-datum skickas i IMAP-format
    Given att jag är ansluten till en brevlåda
    When jag söker med since "2024-01-15"
    Then ska servern ha fått sökkriteriet "SINCE 15-Jan-2024"
