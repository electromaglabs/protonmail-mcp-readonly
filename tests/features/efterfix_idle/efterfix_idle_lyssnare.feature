Feature: En långsam lyssnare stoppar inte bevakningen
  Som modell som prenumererar på nya mejl
  vill jag att bevakningen fortsätter direkt efter varje nytt mejl
  så att en session som har slutat läsa inte fördröjer nästa mejl.

  Lyssnarna (t.ex. resursnotiserna) körs som egna uppgifter; bevakningen
  startar om IDLE utan att vänta på dem, och stop() städar även dem.

  Background:
    Given en Bridge med IDLE där INBOX har mejlen 1, 2 och 3
    And att bevakningen av INBOX har startat med en lyssnare som hänger sig

  Scenario: Nästa mejl syns direkt fast lyssnaren inte har svarat
    When ett mejl med ämnet "Först" kommer till INBOX och lyssnaren har anropats
    And ett mejl med ämnet "Sedan" kommer till INBOX
    Then ska händelsekön för INBOX inom 1.0 sekunder innehålla UID:n "4,5"
    And ska lyssnaren ha anropats för båda mejlen

  Scenario: stop avbryter lyssnare som fortfarande körs
    When ett mejl med ämnet "Först" kommer till INBOX och lyssnaren har anropats
    And bevakningen stoppas
    Then ska lyssnaranropet ha avbrutits
    And ska inga bevakningsuppgifter eller notisuppgifter vara kvar
