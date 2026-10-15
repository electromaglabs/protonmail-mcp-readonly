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
