Feature: Permanent radering rapporterar det som faktiskt hände
  Som en MCP-klient
  vill jag att delete_email(permanent=True) svarar "raderat" när mejlen är borta
  och att inga utkast blir kvar osynliga i All Mail,
  även när Bridge först nekar raderingen och genomför den när den synkar med Proton.

  Scenario: Bridge nekar med Code=2501 men raderar ändå
    Given att mejlet "<a@x>" ligger i "Trash" med UID "5" och i All Mail med UID "50"
    And att mejlet "<b@x>" ligger i "Trash" med UID "6" och i All Mail med UID "51"
    And att Bridge svarar NO med Code=2501 på permanent radering i "Trash" men ändå raderar strax efteråt
    When jag raderar UID-listan "5, 6" i "Trash" permanent
    Then ska verktyget svara att UID "5, 6" lyckades
    And ska mejlet "<a@x>" inte finnas i någon vy, inte heller All Mail
    And ska Bridge aldrig ha fått EXPUNGE utan UID

  Scenario: Mejlet finns kvar efter väntan och rapporteras som misslyckat
    Given att mejlet "<a@x>" ligger i "Trash" med UID "5" och i All Mail med UID "50"
    And att Bridge svarar NO med Code=2501 på permanent radering i "Trash" och mejlen blir kvar
    When jag raderar mejlet med UID "5" i "Trash" permanent
    Then ska verktyget ge ett fel som nämner "finns kvar i Trash"
    And ska mejlet "<a@x>" bara ligga i "Trash, All Mail"

  Scenario: Ett utkast som blir föräldralöst i All Mail raderas via Trash
    Given att utkastet "<d@x>" ligger i "Trash" med UID "6" och i All Mail med UID "51"
    And att Bridge svarar NO med Code=2501 på permanent radering i "Trash" men ändå raderar strax efteråt
    When jag raderar mejlet med UID "6" i "Trash" permanent
    Then ska verktyget svara att det lyckades
    And ska mejlet "<d@x>" inte finnas i någon vy, inte heller All Mail
