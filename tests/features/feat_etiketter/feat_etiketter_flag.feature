Feature: Stjärnmärka mejl
  Som en MCP-klient
  vill jag kunna stjärnmärka och avmarkera mejl
  så att de syns under Starred i Proton.

  Scenario: Stjärnmärkning sätter \Flagged på just det mejlet
    Given att mejlet med UID "42" och Message-ID "<a@x>" ligger i "INBOX"
    When jag stjärnmärker UID "42" i "INBOX"
    Then ska verktyget svara att det lyckades
    And ska Bridge ha fått "UID STORE" med "42 +FLAGS (\Flagged)"

  Scenario: Avmarkering tar bort \Flagged och mejlet ligger kvar
    Given att mejlet med UID "42" och Message-ID "<a@x>" ligger i "INBOX"
    When jag tar bort stjärnmärkningen på UID "42" i "INBOX"
    Then ska verktyget svara att det lyckades
    And ska Bridge ha fått "UID STORE" med "42 -FLAGS (\Flagged)"
    And ska mejlet med Message-ID "<a@x>" ligga i "INBOX"
    And ska Bridge inte ha fått "UID EXPUNGE"

  Scenario: Ett UID som inte finns ger fel i stället för "lyckades"
    When jag stjärnmärker UID "99999" i "INBOX"
    Then ska verktyget ge ett fel som nämner "Inget meddelande med UID 99999 i INBOX"
    And ska Bridge inte ha fått något skrivkommando
