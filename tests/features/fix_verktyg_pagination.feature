Feature: Sidindelning av e-postlistan
  Som en MCP-klient
  vill jag att list_emails avvisar orimliga sidparametrar och aldrig upprepar brev
  så att jag kan bläddra igenom en mapp utan dubbletter eller kryptiska fel.

  Scenario: Sidstorlek noll avvisas med ett tydligt valideringsfel
    Given att mappen INBOX innehåller 12 meddelanden
    When jag anropar list_emails med page 1 och page_size 0
    Then ska anropet avvisas med ett valideringsfel om "page_size"
    And ingen IMAP-hämtning ska ha gjorts

  Scenario: Sidstorlek över taket avvisas
    Given att mappen INBOX innehåller 12 meddelanden
    When jag anropar list_emails med page 1 och page_size 101
    Then ska anropet avvisas med ett valideringsfel om "page_size"

  Scenario: Sidnummer noll avvisas
    Given att mappen INBOX innehåller 12 meddelanden
    When jag anropar list_emails med page 0 och page_size 5
    Then ska anropet avvisas med ett valideringsfel om "page"

  Scenario: En sida förbi slutet ger en tom lista i stället för det äldsta brevet
    Given att mappen INBOX innehåller 12 meddelanden
    When jag anropar list_emails med page 99 och page_size 5
    Then ska resultatet ha en tom meddelandelista
    And has_more ska vara falskt
    And total ska vara 12 och pages 3
