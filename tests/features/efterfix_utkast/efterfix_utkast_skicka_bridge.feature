Feature: send_draft räknar med att Bridge själv tar bort det skickade utkastet
  Som en användare som skickar ett granskat utkast
  vill jag att svaret säger rätt om utkastet togs bort
  så att jag inte får en falsk varning när Bridge redan har tagit bort det.

  Bridge lägger till <utkastets-id@protonmail.internalid> i References när ett utkast
  hämtas, och tar själv bort det refererade utkastet efter ett lyckat skick.

  Background:
    Given mitt konto är "me@proton.me"
    And ett utkast från Proton med det interna id:t "utkast-7" till "asa@example.se"

  Scenario: Har Bridge redan tagit bort utkastet räknas det som borttaget
    Given att Bridge tar bort utkastet ur Drafts när det skickas
    When jag skickar utkastet
    Then SMTP-mottagarna ska vara "asa@example.se"
    And ska Drafts innehålla 0 utkast
    And svaret ska ange att utkastet togs bort utan varning
    And inget UID STORE eller UID EXPUNGE ska ha skickats

  Scenario: Finns utkastet kvar efter skicket tar send_draft bort det
    When jag skickar utkastet
    Then ska Drafts innehålla 0 utkast
    And svaret ska ange att utkastet togs bort utan varning

  Scenario: Hinner Bridge ta bort utkastet medan send_draft raderar det blir det ingen varning
    Given att Bridge tar bort utkastet och svarar NO när send_draft raderar det
    When jag skickar utkastet
    Then ska Drafts innehålla 0 utkast
    And svaret ska ange att utkastet togs bort utan varning

  Scenario: Har Bridge tagit bort utkastet i Proton men inte hunnit synka Drafts blir det ingen varning
    Given att Bridge svarar NO på "EXPUNGE"
    When jag skickar utkastet
    Then SMTP-mottagarna ska vara "asa@example.se"
    And svaret ska ange att utkastet togs bort utan varning
    And svaret ska förklara att Bridge tar bort utkastet själv
