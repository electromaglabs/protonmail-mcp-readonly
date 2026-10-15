Feature: Permanent radering räknas som klar först när mejlet är borta ur All Mail
  Som en MCP-klient
  vill jag att delete_email(permanent=True) bara svarar "raderat" för mejl som verkligen är raderade,
  eftersom Bridge vid Code=2501 avbryter hela omgången före raderingen och då lämnar
  vanliga mejl kvar i All Mail utan mapp, osynliga i alla andra mappar.

  Scenario: Ett vanligt mejl i samma omgång som ett redan raderat mejl raderas på riktigt
    Given att mejlet "<gone@x>" ligger i "Trash" med UID "5" och i All Mail med UID "50"
    And att mejlet "<gone@x>" redan är raderat i Proton men fortfarande syns i Bridge
    And att mejlet "<keep@x>" ligger i "Trash" med UID "6" och i All Mail med UID "51"
    And att Bridge svarar NO med Code=2501 på permanent radering i "Trash" och avbryter omgången
    When jag raderar UID-listan "5, 6" i "Trash" permanent
    Then ska verktyget svara att UID "5, 6" lyckades
    And ska mejlet "<keep@x>" inte finnas i någon vy, inte heller All Mail
    And ska mejlet "<gone@x>" inte finnas i någon vy, inte heller All Mail
    And ska Bridge aldrig ha fått EXPUNGE utan UID

  Scenario: Ett ensamt vanligt mejl som blev kvar i All Mail raderas via Trash
    Given att mejlet "<keep@x>" ligger i "Trash" med UID "6" och i All Mail med UID "51"
    And att Bridge svarar NO med Code=2501 på permanent radering i "Trash" och avbryter omgången
    When jag raderar mejlet med UID "6" i "Trash" permanent
    Then ska verktyget svara att det lyckades
    And ska mejlet "<keep@x>" inte finnas i någon vy, inte heller All Mail

  Scenario: Går det inte att kontrollera All Mail blir det ett fel i stället för "raderat"
    Given att mejlet "<keep@x>" ligger i "Trash" med UID "6" och i All Mail med UID "51"
    And att Bridge svarar NO med Code=2501 på permanent radering i "Trash" och avbryter omgången
    And att Bridge nekar sökningar
    When jag raderar UID-listan "6" i "Trash" permanent
    Then ska inget UID ha lyckats
    And ska verktyget ge ett fel som nämner "All Mail"
    And ska mejlet "<keep@x>" bara ligga i "All Mail"

  Scenario: Flera likadana mejl i All Mail gör att raderingen inte kan bekräftas
    Given att Bridge inte visar X-Pm-Internal-Id
    And att mejlet "<keep@x>" ligger i "Trash" med UID "6" och i All Mail med UID "51"
    And att ett annat mejl "tvillingen" med samma Message-ID "<keep@x>", tid och storlek ligger i "Archive" med UID "3"
    And att mejlet "tvillingen" också syns i "All Mail" med UID "52"
    And att Bridge svarar NO med Code=2501 på permanent radering i "Trash" och avbryter omgången
    When jag raderar UID-listan "6" i "Trash" permanent
    Then ska inget UID ha lyckats
    And ska verktyget ge ett fel som nämner "All Mail"
    And ska mejlet "tvillingen" bara ligga i "Archive, All Mail"
