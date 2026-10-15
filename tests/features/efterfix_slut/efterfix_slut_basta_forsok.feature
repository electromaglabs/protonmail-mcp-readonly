Feature: Ett misslyckat följdsteg gör inte ett lyckat anrop till ett fel
  Som en MCP-klient
  vill jag att unflag_email och delete_email(permanent=True) redovisar vad som faktiskt
  hände när ett följdsteg hänger eller anslutningen bryts, i stället för att hela anropet
  ser misslyckat ut eller att det som redan är klart försvinner ur svaret.

  Scenario: En timeout när mejlet tas bort ur Starred gör inte avmarkeringen till ett fel
    Given att mejlet "<a@x>" är stjärnmärkt med UID "1" i "INBOX" och UID "7" i Starred
    And att Bridge inte svarar på sökningar i "Starred"
    When jag tar bort stjärnmärkningen på UID "1" i "INBOX"
    Then ska verktyget svara att det lyckades
    And ska svaret ha en förklaring som nämner "Starred"
    And ska mejlet "<a@x>" inte vara stjärnmärkt

  Scenario: En timeout i kontrollen i All Mail ger ett fel per mejl, inte ett fel för hela raderingen
    Given att mejlet "<keep@x>" ligger i "Trash" med UID "6" och i All Mail med UID "51"
    And att Bridge svarar NO med Code=2501 på permanent radering i "Trash" och avbryter omgången
    And att Bridge inte svarar på sökningar i "All Mail"
    When jag raderar UID-listan "6" i "Trash" permanent
    Then ska inget UID ha lyckats
    And ska verktyget ge ett fel som nämner "All Mail"
