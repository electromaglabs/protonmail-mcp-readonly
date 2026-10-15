Feature: Avbrott når fram även i utkasten och bevakningen
  Som MCP-server
  vill jag att ett avbrutet anrop slutar direkt även när avbrottet kommer i samma ögonblick
  som det anropet väntar på blir klart, så att inget fortsätter i bakgrunden.

  Scenario: Väntan på nya mejl avbryts när bevakningen vaknar samtidigt
    Given en bevakning av "INBOX" som inte har några nya mejl
    And att en klient väntar på nya mejl i "INBOX"
    When bevakningen vaknar utan nya mejl i samma ögonblick som klienten avbryter
    Then ska väntan sluta som avbruten inom några sekunder

  Scenario: Sparandet av ett utkast avbryts när Bridge svarar på APPEND
    Given en IMAP-klient där Bridge aldrig svarar på sökningar
    When klienten avbryter i samma ögonblick som Bridge svarar på APPEND av ett utkast
    Then ska sparandet sluta som avbrutet inom några sekunder
