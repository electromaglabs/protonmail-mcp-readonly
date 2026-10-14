Feature: Strängen "null" är ett sökord, inte ett utelämnat filter
  Som en MCP-klient
  vill jag att search_emails söker på exakt den text jag skickar
  så att ett ämne som "null" inte tyst blir en sökning utan ämnesfilter.

  Scenario: Sökning på ämnet "null" skickar ordet vidare som filter
    Given att jag är ansluten till brevlådan
    When jag söker i INBOX med subject "null"
    Then ska IMAP-sökningen få subject "null"

  Scenario: Ett uttryckligt null betyder fortfarande inget filter
    Given att jag är ansluten till brevlådan
    When jag söker i INBOX med from_addr satt till JSON-null
    Then ska IMAP-sökningen få from_addr None
