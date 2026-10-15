Feature: Att ta bort en stjärna rör inte ett annat mejls stjärna
  Som en MCP-klient
  vill jag att unflag_email bara tar bort stjärnan från det mejl jag angav,
  även när ett annat mejl har samma Message-ID, tid och storlek och är stjärnmärkt.

  Scenario: Avmarkering av ett ostjärnmärkt mejl lämnar tvillingens stjärna kvar
    Given att mejlet "<a@x>" ligger i "INBOX" med UID "1" och i All Mail med UID "50"
    And att ett annat mejl "tvillingen" med samma Message-ID "<a@x>", tid och storlek är stjärnmärkt i "Archive" med UID "3" och i Starred med UID "7"
    When jag tar bort stjärnmärkningen på UID "1" i "INBOX"
    Then ska verktyget svara att det lyckades
    And ska mejlet "tvillingen" vara stjärnmärkt
    And ska mejlet "tvillingen" bara ligga i "Archive, Starred"

  Scenario: Även utan X-Pm-Internal-Id lämnas tvillingens stjärna kvar
    Given att Bridge inte visar X-Pm-Internal-Id
    And att mejlet "<a@x>" ligger i "INBOX" med UID "1" och i All Mail med UID "50"
    And att ett annat mejl "tvillingen" med samma Message-ID "<a@x>", tid och storlek är stjärnmärkt i "Archive" med UID "3" och i Starred med UID "7"
    When jag tar bort stjärnmärkningen på UID "1" i "INBOX"
    Then ska verktyget svara att det lyckades
    And ska mejlet "tvillingen" vara stjärnmärkt
    And ska mejlet "tvillingen" bara ligga i "Archive, Starred"

  Scenario: Det avmarkerade mejlet försvinner fortfarande ur Starred
    Given att mejlet "<a@x>" är stjärnmärkt med UID "1" i "INBOX" och UID "7" i Starred
    When jag tar bort stjärnmärkningen på UID "1" i "INBOX"
    Then ska verktyget svara att det lyckades
    And ska mejlet "<a@x>" inte vara stjärnmärkt
    And ska mejlet "<a@x>" bara ligga i "INBOX"
