Feature: Svar på ett mejl till sig själv
  Som en MCP-klient
  vill jag kunna svara på ett mejl som jag skickat till mig själv
  så att svaret hamnar hos mig i stället för att verktyget säger att mottagare saknas.

  Scenario: Svar på ett mejl från det egna kontot till det egna kontot
    Given att mejlet med UID "3" i "INBOX" är från "me@proton.me" till "me@proton.me"
    When jag svarar på UID "3" i "INBOX"
    Then ska svaret skickas till "me@proton.me"
    And ska svaret ha ämnet "Re: Påminnelse"

  Scenario: Svarsutkast på ett mejl till sig själv
    Given att mejlet med UID "3" i "INBOX" är från "me@proton.me" till "me@proton.me"
    When jag skapar ett svarsutkast på UID "3" i "INBOX"
    Then ska utkastet ha mottagaren "me@proton.me"

  Scenario: Eget mejl till någon annan går fortfarande till den mottagaren
    Given att mejlet med UID "3" i "INBOX" är från "me@proton.me" till "anna@example.com"
    When jag svarar på UID "3" i "INBOX"
    Then ska svaret skickas till "anna@example.com"
