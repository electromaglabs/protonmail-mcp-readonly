Feature: Sökträffar har mottagare och Message-ID
  Som en MCP-klient
  vill jag att sökträffarna har samma metadata som list_emails,
  eftersom ett tomt "to" och "message_id" ser ut som riktiga värden.

  Scenario: En sökträff visar mottagare och Message-ID
    Given att mejlet med UID "5" i "INBOX" är skickat till "anna@example.se" med Message-ID "<abc@example.se>"
    When jag söker efter olästa mejl i "INBOX"
    Then ska träffen med UID "5" ha to "anna@example.se" och message_id "<abc@example.se>"
