Feature: Strängen "null" som HTML-text
  Som en MCP-klient
  vill jag att en HTML-text som råkar vara "null" skickas som text
  så att innehållet inte tyst försvinner.

  Scenario: send_email med HTML-texten "null"
    Given en MCP-klient med attrapp för SMTP
    When jag anropar verktyget send_email med HTML-texten "null"
    Then ska SMTP-klienten få HTML-texten "null"

  Scenario: reply_to_email med HTML-texten "null"
    Given en MCP-klient med attrapp för SMTP
    When jag anropar verktyget reply_to_email med HTML-texten "null"
    Then ska SMTP-klientens HTML-text börja med "null"
