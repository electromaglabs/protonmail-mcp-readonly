Feature: Markera mejl som läst eller oläst
  Som en MCP-klient
  vill jag få veta om markeringen faktiskt gjordes
  i stället för ett "lyckades" för ett mejl som inte finns.

  Scenario: Markera ett befintligt mejl som läst
    Given att mejlet med UID "42" ligger i "INBOX"
    When jag markerar mejlet med UID "42" i "INBOX" som läst
    Then ska verktyget svara att det lyckades
    And ska Bridge ha fått "UID STORE" med "42 +FLAGS (\Seen)"

  Scenario: Ett UID som inte finns ger fel i stället för "lyckades"
    When jag markerar mejlet med UID "99999" i "INBOX" som läst
    Then ska verktyget ge ett fel som nämner "Inget meddelande med UID 99999 i INBOX"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Om Bridge nekar markeringen får klienten veta varför
    Given att mejlet med UID "42" ligger i "INBOX"
    And att Bridge nekar STORE med "backend error"
    When jag markerar mejlet med UID "42" i "INBOX" som oläst
    Then ska verktyget ge ett fel som nämner "backend error"
