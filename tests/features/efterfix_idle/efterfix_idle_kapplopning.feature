Feature: Bevakningen missar inga mejl som kommer medan den hämtar eller förnyar
  Som modell som väntar på nya mejl
  vill jag att varje nytt mejl syns direkt
  så att jag inte svarar "inga nya mejl" när ett mejl faktiskt har kommit.

  Bridge skickar köade uppdateringar (* n EXISTS) i svaret på nästa kommando
  i mappen och aldrig igen. Kommer ett mejl medan bevakningen söker eller
  hämtar, hamnar EXISTS i det svaret i stället för i IDLE. Kommer det mellan
  DONE och OK vid förnyelsen, hamnar det i IDLE-kön för den omgång som just
  avslutas.

  Background:
    Given en Bridge med IDLE där INBOX har mejlen 1, 2 och 3

  Scenario: Ett mejl som kommer medan bevakningen hämtar ett annat syns direkt
    Given att bevakningen av INBOX har startat med förnyelse var 60.0 sekunder
    When ett mejl kommer till INBOX och ett till kommer medan bevakningen hämtar det första
    Then ska händelsekön för INBOX inom 2.0 sekunder innehålla UID:n "4,5"

  Scenario: Ett mejl som kommer medan bevakningen söker syns direkt
    Given att bevakningen av INBOX har startat med förnyelse var 60.0 sekunder
    When ett mejl kommer till INBOX och ett till kommer medan bevakningen söker efter det första
    Then ska händelsekön för INBOX inom 2.0 sekunder innehålla UID:n "4,5"

  Scenario: Ett mejl som kommer precis när IDLE förnyas syns direkt
    Given att bevakningen av INBOX har startat med förnyelse var 0.3 sekunder
    When ett mejl kommer till INBOX precis när IDLE förnyas
    Then ska händelsekön för INBOX inom 2.0 sekunder innehålla UID:n "4"

  Scenario: check_new_emails visar mejlet som kom under hämtningen
    Given att bevakningen av INBOX har startat med förnyelse var 60.0 sekunder
    And att check_new_emails har anropats för INBOX
    When ett mejl kommer till INBOX och ett till kommer medan bevakningen hämtar det första
    And det har gått 1.0 sekunder
    And jag anropar check_new_emails för INBOX
    Then ska svaret innehålla UID:n "5,4"
