Feature: wait_for_new_email håller sin tidsgräns även när Bridge hänger
  Som modell som väntar på ett mejl med en tidsgräns
  vill jag få svar inom ungefär den tid jag angav
  så att ett Bridge som hänger sig inte låser mig, eller andra verktyg, i minuter.

  Utan bevakning frågar verktyget Bridge direkt. Varje steg (hälsning,
  SELECT, SEARCH) har IMAP-tidsgränsen, men väntan som helhet får inte gå
  mer än några sekunder över timeout_seconds.

  Scenario: Bridge hänger sig mitt i sökningen
    Given en Bridge med IDLE där INBOX har mejlen 1, 2 och 3
    And att bevakningen är avstängd och IMAP-tidsgränsen är 10 sekunder
    And att check_new_emails har anropats för INBOX
    And att Bridge hänger sig på "UID SEARCH"
    When jag väntar på nya mejl i INBOX i högst 1 sekunder
    Then ska anropet ha gett ett fel om att Bridge inte svarade inom 5 sekunder
    And ska verktygens delade anslutning vara släppt
    When Bridge svarar igen
    And jag anropar check_new_emails för INBOX
    Then ska svaret inte innehålla några mejl

  Scenario: Bridge tar emot anslutningen men skickar aldrig någon hälsning
    Given en Bridge som tar emot anslutningar men aldrig svarar
    And att bevakningen är avstängd och IMAP-tidsgränsen är 10 sekunder
    When jag väntar på nya mejl i INBOX i högst 1 sekunder
    Then ska anropet ha gett ett fel om att Bridge inte svarade inom 5 sekunder
    And ska verktygens delade anslutning vara släppt
