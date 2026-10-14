Feature: Ta bort ett mejl till papperskorgen
  Som en MCP-klient
  vill jag att "ta bort" flyttar mejlet till papperskorgen som i Protons egna appar,
  och att permanent radering bara sker när jag uttryckligen ber om det.

  Scenario: Ta bort flyttar mejlet till Trash
    Given att mejlet med UID "42" ligger i "INBOX"
    When jag tar bort mejlet med UID "42" i "INBOX"
    Then ska verktyget svara att det lyckades
    And ska Bridge ha fått "UID MOVE" med "42 "Trash""
    And ska Bridge inte ha fått "EXPUNGE"
    And ska Bridge inte ha fått "UID EXPUNGE"

  Scenario: Ta bort ett mejl som redan ligger i Trash kräver uttrycklig permanent radering
    Given att mejlet med UID "7" ligger i "Trash"
    When jag tar bort mejlet med UID "7" i "Trash"
    Then ska verktyget ge ett fel som nämner "permanent=True"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Permanent radering i Trash tar bara bort det mejlet
    Given att mejlet med UID "7" ligger i "Trash"
    When jag raderar mejlet med UID "7" i "Trash" permanent
    Then ska verktyget svara att det lyckades
    And ska Bridge ha fått "UID STORE" med "7 +FLAGS (\Deleted)"
    And ska Bridge ha fått "UID EXPUNGE" med "7"
    And ska Bridge inte ha fått "EXPUNGE"

  Scenario: Permanent radering utanför Trash och Drafts avvisas
    Given att mejlet med UID "42" ligger i "INBOX"
    When jag raderar mejlet med UID "42" i "INBOX" permanent
    Then ska verktyget ge ett fel som nämner "bara i Trash"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Ta bort i All Mail avvisas med en begriplig förklaring
    Given att mejlet med UID "7" ligger i "All Mail"
    When jag tar bort mejlet med UID "7" i "All Mail"
    Then ska verktyget ge ett fel som nämner "All Mail"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Ett UID som inte finns ger fel i stället för "lyckades"
    When jag tar bort mejlet med UID "99999" i "INBOX"
    Then ska verktyget ge ett fel som nämner "Inget meddelande med UID 99999 i INBOX"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Om den permanenta raderingen nekas tas borttagningsmarkeringen bort igen
    Given att mejlet med UID "7" ligger i "Trash"
    And att Bridge nekar EXPUNGE med "operation not allowed"
    When jag raderar mejlet med UID "7" i "Trash" permanent
    Then ska verktyget ge ett fel som nämner "operation not allowed"
    And ska Bridge ha fått "UID STORE" med "7 -FLAGS (\Deleted)"
