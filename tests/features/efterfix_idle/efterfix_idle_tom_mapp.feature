Feature: Nya mejl i en tom mapp
  Som modell som håller koll på en mapp som ofta är tom (inbox zero, en etikett)
  vill jag att verktygen och bevakningen fungerar även när mappen är tom
  så att jag inte får ett fel i stället för "inga nya mejl".

  Bridge svarar "NO no such message" på UID SEARCH UID n:* i en mapp utan
  mejl, i stället för ett tomt svar.

  Background:
    Given en Bridge med IDLE där INBOX har mejlen 1, 2 och 3
    And att Bridge har den tomma mappen "Labels/Tom" och mappen "Folders/Kunder" med mejlet 7

  Scenario: check_new_emails i en tom mapp som inte bevakas
    Given att servern bara bevakar INBOX
    And att check_new_emails har anropats för "Labels/Tom"
    When jag anropar check_new_emails för "Labels/Tom"
    Then ska svaret inte innehålla några mejl

  Scenario: wait_for_new_email i en tom mapp som inte bevakas går ut utan fel
    Given att servern bara bevakar INBOX
    And att check_new_emails har anropats för "Labels/Tom"
    When jag väntar på nya mejl i "Labels/Tom" i högst 1 sekunder
    Then ska väntan ha gått ut utan fel

  Scenario: Ett mejl som försvinner ur en bevakad tom mapp innan bevakningen söker
    Given att servern bevakar "Labels/Tom"
    When ett mejl kommer till "Labels/Tom" och flyttas bort innan bevakningen hinner söka
    Then ska bevakningen fortfarande bevaka "Labels/Tom" utan fel
    When ett mejl med ämnet "Stannar" kommer till "Labels/Tom"
    Then ska händelsekön för "Labels/Tom" innehålla mejlet med ämnet "Stannar"

  Scenario: Bevakningen återansluter till en mapp som har tömts
    Given att servern bevakar "Folders/Kunder"
    When mejlet 7 flyttas bort ur "Folders/Kunder"
    And Bridge startas om
    Then ska bevakningen ha återanslutit till "Folders/Kunder" utan fel
