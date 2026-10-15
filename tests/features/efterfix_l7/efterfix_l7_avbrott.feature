Feature: Ett avbrutet verktygsanrop släpper IMAP-anslutningen direkt
  Som MCP-server som tar emot flera verktygsanrop
  vill jag att ett anrop som klienten avbryter slutar direkt och släpper låset,
  även när avbrottet kommer i samma ögonblick som Bridge svarar,
  så att nästa verktygsanrop inte behöver vänta på en tidsgräns på 30 s.

  Scenario: Avbrottet kommer precis när Bridge svarar på NOOP
    Given en IMAP-klient där Bridge aldrig svarar på UID-kommandon
    And att klienten avbryter anropet i samma ögonblick som Bridge svarar på NOOP
    When jag markerar mejlet med UID "1" i "INBOX" som läst
    Then ska anropet sluta som avbrutet inom några sekunder
    And ska nästa anrop kunna ta låset direkt
    And ska markeringen aldrig ha skickats till Bridge
