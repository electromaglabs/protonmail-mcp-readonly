Feature: Borttagen stjärna syns direkt i Starred
  Som en MCP-klient
  vill jag att ett mejl försvinner ur Starred när jag tar bort stjärnan
  även om Bridge hämtar ändringen från Proton först en knapp minut senare.

  Scenario: Avmarkering i INBOX tar bort mejlet ur Starred men inte ur INBOX
    Given att mejlet "<a@x>" är stjärnmärkt med UID "1" i "INBOX" och UID "7" i Starred
    When jag tar bort stjärnmärkningen på UID "1" i "INBOX"
    Then ska verktyget svara att det lyckades
    And ska mejlet "<a@x>" inte vara stjärnmärkt
    And ska mejlet "<a@x>" bara ligga i "INBOX"
    And ska Bridge aldrig ha fått EXPUNGE utan UID

  Scenario: Avmarkering med UID:t från Starred
    Given att mejlet "<a@x>" är stjärnmärkt med UID "1" i "INBOX" och UID "7" i Starred
    When jag tar bort stjärnmärkningen på UID "7" i "Starred"
    Then ska verktyget svara att det lyckades
    And ska mejlet "<a@x>" bara ligga i "INBOX"

  Scenario: Andra stjärnmärkta mejl ligger kvar i Starred
    Given att mejlet "<a@x>" är stjärnmärkt med UID "1" i "INBOX" och UID "7" i Starred
    And att mejlet "<b@x>" är stjärnmärkt med UID "2" i "INBOX" och UID "8" i Starred
    When jag tar bort stjärnmärkningen på UID-listan "1" i "INBOX"
    Then ska verktyget svara att UID "1" lyckades
    And ska mejlet "<b@x>" bara ligga i "INBOX, Starred"
