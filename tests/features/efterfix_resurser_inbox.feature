Feature: INBOX är samma resurs oavsett skiftläge
  Som MCP-klient som prenumererar på inkorgen
  vill jag få notiser oavsett om jag skriver INBOX, Inbox eller inbox
  eftersom IMAP (RFC 3501) och Bridge inte skiljer på skiftläge i namnet INBOX,
  och resursen går att läsa med alla stavningarna.

  Scenario Outline: En prenumeration på inkorgen med annat skiftläge får notisen
    Given att klienten prenumererar på resursen "<uri>"
    When bevakaren meddelar nya mejl i "INBOX"
    Then ska klienten få en notis om att "<uri>" har ändrats

    Examples:
      | uri             |
      | mailbox://inbox |
      | mailbox://Inbox |
      | mailbox://INBOX |

  Scenario: Ett mejl i inkorgen är samma resurs oavsett skiftläge
    Given att klienten prenumererar på resursen "email://inbox/42"
    When servern meddelar att resursen "email://INBOX/42" har ändrats
    Then ska klienten få en notis om att "email://inbox/42" har ändrats

  Scenario: Andra mappnamn jämförs fortfarande exakt
    Given att klienten prenumererar på resursen "mailbox://archive"
    When servern meddelar att resursen "mailbox://Archive" har ändrats
    Then ska klienten inte få någon notis
