Feature: Konfigurerbar IMAP-timeout
  Som användare med ett stort konto
  vill jag kunna ge långsamma sökningar mer tid
  så att en SEARCH i All Mail inte avbryts efter 10 sekunder.

  Scenario: Standardtiden räcker för Bridges söktider
    Given att ingen IMAP-timeout är inställd
    When inställningarna läses
    Then ska IMAP-timeouten vara 30 sekunder

  Scenario: Timeouten kan höjas via miljövariabel
    Given att PROTONMAIL_IMAP_TIMEOUT är "120"
    When inställningarna läses
    Then ska IMAP-timeouten vara 120 sekunder
