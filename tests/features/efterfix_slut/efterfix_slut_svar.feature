Feature: Ett mejl räknas som mitt eget bara om det bevisligen skickats från kontot
  Som en MCP-klient
  vill jag att ett svar på ett mejl som bara påstår sig vara från mitt konto (förfalskad From)
  behandlas som ett vanligt mottaget mejl, så att svaret inte går till de adresser
  som förfalskaren skrev i To.

  Scenario: Ett förfalskat mejl "från mig" till en lookalike-adress
    Given mitt konto är "me@proton.me"
    And att mejlet med UID "3" i "INBOX" är från "me@proton.me" till "ekonomi@pr0ton-me.com" och märkt "X-Pm-Origin: external"
    When jag svarar på UID "3" i "INBOX"
    Then ska svaret inte skickas till "ekonomi@pr0ton-me.com"
    And ska svaret skickas till "me@proton.me"

  Scenario: Ett eget skickat mejl går till sin mottagare
    Given mitt konto är "me@proton.me"
    And att mejlet med UID "3" i "Sent" är från "me@proton.me" till "anna@example.com" och märkt "X-Pm-Origin: internal"
    When jag svarar på UID "3" i "Sent"
    Then ska svaret skickas till "anna@example.com"

  Scenario: Ett eget mejl utan märkning som finns i Sent går till sin mottagare
    Given mitt konto är "me@proton.me"
    And att mejlet med UID "3" i "INBOX" är från "me@proton.me" till "anna@example.com" och samma Proton-mejl finns i Sent
    When jag svarar på UID "3" i "INBOX"
    Then ska svaret skickas till "anna@example.com"
