Feature: Nya mejl ger resursnotiser
  Som MCP-klient som prenumererar på en mapp
  vill jag få notifications/resources/updated när ett nytt mejl kommer
  så att jag kan läsa om mappen direkt i stället för att fråga om och om igen.

  Background:
    Given en Bridge med IDLE där INBOX har mejlen 1, 2 och 3
    And en klient som är ansluten till servern och prenumererar på "mailbox://INBOX"

  Scenario: Ett nytt mejl i en prenumererad mapp ger en notis
    When ett mejl kommer till INBOX
    Then ska klienten få notisen resources/updated för "mailbox://INBOX"

  Scenario: Ett mejl i en mapp utan prenumeration ger ingen notis
    Given att servern även bevakar "Folders/Kunder"
    When ett mejl kommer till "Folders/Kunder"
    Then ska klienten inte få någon notis
