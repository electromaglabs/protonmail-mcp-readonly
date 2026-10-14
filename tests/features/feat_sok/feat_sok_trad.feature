Feature: Hämta en hel konversation med get_thread
  Som en MCP-klient
  vill jag kunna hämta alla mejl i samma konversation som ett mejl
  för att förstå sammanhanget innan jag svarar.

  Bridge saknar IMAP THREAD. Konversationen byggs av Message-ID,
  In-Reply-To och References, och söks i All Mail så att både mottagna
  och skickade mejl kommer med.

  Background:
    Given en brevlåda "All Mail" med mejlen
      | uid  | from               | subject          | date                            | message_id | in_reply_to | references      |
      | 1001 | anna@example.com   | Offert           | Mon, 05 Oct 2026 09:00:00 +0200 | <a@x>      |             |                 |
      | 1002 | m@neomeda.se       | Re: Offert       | Mon, 05 Oct 2026 10:00:00 +0200 | <b@x>      | <a@x>       | <a@x>           |
      | 1003 | anna@example.com   | Re: Re: Offert   | Tue, 06 Oct 2026 08:00:00 +0200 | <c@x>      | <b@x>       | <a@x> <b@x>     |
      | 1004 | bo@example.com     | Annat ärende     | Tue, 06 Oct 2026 09:00:00 +0200 | <d@x>      |             |                 |
      | 1005 | m@neomeda.se       | Re: Re: Offert   | Wed, 07 Oct 2026 08:00:00 +0200 | <e@x>      | <c@x>       | <c@x>           |
    And en brevlåda INBOX där UID "7" är mejlet med Message-ID "<c@x>"

  Scenario: Hela konversationen hämtas från ett mejl mitt i tråden
    When jag hämtar konversationen för UID "7" i INBOX
    Then ska konversationen bestå av All Mail-UID "1001, 1002, 1003, 1005" i datumordning
    And ska varje mejl ha mailbox "All Mail"
    And ska konversationen vara komplett

  Scenario: Taket för antal mejl respekteras
    When jag hämtar konversationen för UID "7" i INBOX med max_messages 2
    Then ska konversationen innehålla 2 mejl
    And ska konversationen inte vara komplett

  Scenario: Ett mejl utan svar är en konversation med ett mejl
    Given en brevlåda INBOX där UID "8" är mejlet med Message-ID "<d@x>"
    When jag hämtar konversationen för UID "8" i INBOX
    Then ska konversationen bestå av All Mail-UID "1004" i datumordning

  Scenario: Ett UID som inte finns ger ett begripligt fel
    When jag hämtar konversationen för UID "999" i INBOX
    Then ska hämtningen avvisas med "Inget meddelande med UID 999"
