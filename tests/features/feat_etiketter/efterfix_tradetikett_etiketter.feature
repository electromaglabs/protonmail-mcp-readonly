Feature: remove_label och add_label ger rätt svar per UID i svåra fall
  Som en MCP-klient
  vill jag att etikettverktygen rapporterar exakt vilka mejl som ändrades
  så att jag inte gör om eller missar något.

  Scenario: Bridge hinner ta bort etiketten från några mejl innan UID EXPUNGE nekas
    Given att etiketten "Labels/Kvitton" finns
    And att mejlet med UID "41" och Message-ID "<a@x>" ligger i "INBOX"
    And att mejlet med Message-ID "<a@x>" har etiketten "Labels/Kvitton" med UID "7"
    And att mejlet med UID "42" och Message-ID "<b@x>" ligger i "INBOX"
    And att mejlet med Message-ID "<b@x>" har etiketten "Labels/Kvitton" med UID "8"
    And att Bridge tar bort etiketten från UID "7" men sedan nekar UID EXPUNGE med "backend error"
    When jag tar bort etiketten "Kvitton" från UID-listan "41, 42" i "INBOX"
    Then ska resultatet ha ok "41" och UID "42" misslyckat med "backend error"
    And ska mejlet med Message-ID "<a@x>" inte ligga i "Labels/Kvitton"
    And ska mejlet med Message-ID "<b@x>" ligga i "Labels/Kvitton"
    And ska Bridge ha fått "UID STORE" med "8 -FLAGS (\Deleted)"

  Scenario: Ett vikt Message-ID med kommentar stoppar inte massborttagningen
    Given att etiketten "Labels/Kvitton" finns
    And att mejlet med UID "41" har det vikta Message-ID:t "<c@x>" med kommentaren "(kommentar)" i "INBOX" och i "Labels/Kvitton" med UID "9"
    And att mejlet med UID "42" och Message-ID "<b@x>" ligger i "INBOX"
    And att mejlet med Message-ID "<b@x>" har etiketten "Labels/Kvitton" med UID "8"
    When jag tar bort etiketten "Kvitton" från UID-listan "41, 42" i "INBOX"
    Then ska resultatet ha ok "41, 42" och inga misslyckade

  Scenario: Ett mejl vars Message-ID inte går att söka på ger fel bara för det UID:t
    Given att etiketten "Labels/Kvitton" finns
    And att mejlet med UID "41" har det tomma Message-ID:t "   " i "INBOX"
    And att mejlet med UID "42" och Message-ID "<b@x>" ligger i "INBOX"
    And att mejlet med Message-ID "<b@x>" har etiketten "Labels/Kvitton" med UID "8"
    When jag tar bort etiketten "Kvitton" från UID-listan "41, 42" i "INBOX"
    Then ska resultatet ha ok "42" och UID "41" misslyckat med "saknar Message-ID"

  Scenario: En etikett som finns med annan versal används i stället för att en dubblett föreslås
    Given att etiketten "Labels/Faktura" finns
    And att mejlet med UID "42" och Message-ID "<a@x>" ligger i "INBOX"
    When jag lägger till etiketten "faktura" på UID "42" i "INBOX" med efterfix-steget
    Then ska verktyget svara att det lyckades
    And ska mejlet med Message-ID "<a@x>" ligga i "Labels/Faktura"
    And ska Bridge inte ha fått "CREATE"

  Scenario: remove_label hittar också etiketten med annan versal
    Given att etiketten "Labels/Faktura" finns
    And att mejlet med UID "42" och Message-ID "<a@x>" ligger i "INBOX"
    And att mejlet med Message-ID "<a@x>" har etiketten "Labels/Faktura" med UID "7"
    When jag tar bort etiketten "FAKTURA" från UID-listan "42" i "INBOX"
    Then ska resultatet ha ok "42" och inga misslyckade
    And ska mejlet med Message-ID "<a@x>" inte ligga i "Labels/Faktura"

  Scenario: Flera etiketter med annan versal ger fel som nämner dem, utan råd om att skapa en ny
    Given att etiketten "Labels/Faktura" finns
    And att etiketten "Labels/FAKTURA" finns
    And att mejlet med UID "42" och Message-ID "<a@x>" ligger i "INBOX"
    When jag lägger till etiketten "faktura" på UID "42" i "INBOX" med efterfix-steget
    Then ska verktyget ge ett fel som nämner "Labels/Faktura"
    And ska felet inte nämna "create_folder"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Bara remove_label säger att UID:n som saknar etiketten hamnar i failed
    Then ska beskrivningen av "remove_label" nämna "som saknar etiketten"
    And ska beskrivningen av "add_label" inte nämna "som saknar etiketten"
    And ska beskrivningen av "flag_email" inte nämna "som saknar etiketten"
    And ska beskrivningen av "unflag_email" inte nämna "som saknar etiketten"
