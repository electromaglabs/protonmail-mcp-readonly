Feature: Inställningar för bevakning av nya mejl
  Som användare av MCP-servern
  vill jag kunna välja vilka mappar som bevakas och kunna stänga av bevakningen
  så att servern inte håller fler anslutningar till Bridge än jag vill.

  Varje bevakad mapp är en egen IMAP-anslutning till Bridge, därför finns ett tak.

  Scenario: Standard är att INBOX bevakas
    Given att inga bevakningsinställningar är satta
    Then ska bevakningen vara påslagen
    And ska de bevakade mapparna vara "INBOX"

  Scenario: Flera mappar anges kommaseparerat
    Given att PROTONMAIL_WATCH_MAILBOXES är "INBOX, Folders/Kunder ,Labels/Viktigt"
    Then ska de bevakade mapparna vara "INBOX|Folders/Kunder|Labels/Viktigt"

  Scenario: Samma mapp två gånger bevakas en gång
    Given att PROTONMAIL_WATCH_MAILBOXES är "INBOX,inbox,Folders/A,Folders/A"
    Then ska de bevakade mapparna vara "INBOX|Folders/A"

  Scenario: Fler än fem mappar avvisas
    Given att PROTONMAIL_WATCH_MAILBOXES är "A,B,C,D,E,F"
    Then ska inställningarna avvisas med "högst 5"

  Scenario: En tom lista avvisas
    Given att PROTONMAIL_WATCH_MAILBOXES är " , "
    Then ska inställningarna avvisas med "PROTONMAIL_WATCH_ENABLED=false"

  Scenario: Ett mappnamn med kontrolltecken avvisas
    Given att PROTONMAIL_WATCH_MAILBOXES är "INBOX,Folders/A\rB"
    Then ska inställningarna avvisas med "Ogiltigt mappnamn"

  Scenario: Bevakningen kan stängas av
    Given att PROTONMAIL_WATCH_ENABLED är "false"
    Then ska bevakningen vara avstängd
