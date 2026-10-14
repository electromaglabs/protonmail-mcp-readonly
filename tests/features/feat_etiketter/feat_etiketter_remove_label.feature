Feature: Ta bort en etikett från ett mejl
  Som en MCP-klient
  vill jag kunna ta bort en etikett från ett mejl
  utan att mejlet flyttas, raderas eller förlorar andra etiketter.

  Scenario: Etiketten tas bort med UID EXPUNGE på mejlets UID i etiketten
    Given att etiketten "Labels/Kvitton" finns
    And att mejlet med UID "42" och Message-ID "<a@x>" ligger i "INBOX"
    And att mejlet med Message-ID "<a@x>" har etiketten "Labels/Kvitton" med UID "7"
    When jag tar bort etiketten "Kvitton" från UID "42" i "INBOX"
    Then ska verktyget svara att det lyckades
    And ska Bridge ha fått "UID STORE" med "7 +FLAGS (\Deleted)"
    And ska Bridge ha fått "UID EXPUNGE" med "7"
    And ska mejlet med Message-ID "<a@x>" ligga i "INBOX"
    And ska mejlet med Message-ID "<a@x>" inte ligga i "Labels/Kvitton"
    And ska Bridge inte ha fått "EXPUNGE"

  Scenario: Andra mejl i etiketten berörs inte, inte heller de med liknande Message-ID
    Given att etiketten "Labels/Kvitton" finns
    And att mejlet med UID "42" och Message-ID "<a@x>" ligger i "INBOX"
    And att mejlet med Message-ID "<a@x>" har etiketten "Labels/Kvitton" med UID "7"
    And att mejlet med UID "43" och Message-ID "<ba@x>" ligger i "INBOX"
    And att mejlet med Message-ID "<ba@x>" har etiketten "Labels/Kvitton" med UID "8"
    When jag tar bort etiketten "Kvitton" från UID "42" i "INBOX"
    Then ska verktyget svara att det lyckades
    And ska mejlet med Message-ID "<ba@x>" ligga i "Labels/Kvitton"
    And ska Bridge inte ha fått "UID EXPUNGE" med "8"

  Scenario: Ett mejl som inte har etiketten ger fel och inget ändras
    Given att etiketten "Labels/Kvitton" finns
    And att mejlet med UID "42" och Message-ID "<a@x>" ligger i "INBOX"
    When jag tar bort etiketten "Kvitton" från UID "42" i "INBOX"
    Then ska verktyget ge ett fel som nämner "har inte etiketten Labels/Kvitton"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Etiketten kan tas bort direkt i etikettens egen vy
    Given att etiketten "Labels/Kvitton" finns
    And att mejlet med UID "42" och Message-ID "<a@x>" ligger i "INBOX"
    And att mejlet med Message-ID "<a@x>" har etiketten "Labels/Kvitton" med UID "7"
    When jag tar bort etiketten "Kvitton" från UID "7" i "Labels/Kvitton"
    Then ska verktyget svara att det lyckades
    And ska Bridge ha fått "UID EXPUNGE" med "7"
    And ska mejlet med Message-ID "<a@x>" ligga i "INBOX"

  Scenario: En etikett som inte finns ger fel som hänvisar till create_folder
    Given att mejlet med UID "42" och Message-ID "<a@x>" ligger i "INBOX"
    When jag tar bort etiketten "Saknas" från UID "42" i "INBOX"
    Then ska verktyget ge ett fel som nämner "create_folder("Labels/Saknas")"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Ett UID som inte finns i mappen ger fel
    Given att etiketten "Labels/Kvitton" finns
    When jag tar bort etiketten "Kvitton" från UID "99999" i "INBOX"
    Then ska verktyget ge ett fel som nämner "Inget meddelande med UID 99999 i INBOX"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Om Bridge nekar borttagningen lämnas ingen raderingsmarkering kvar
    Given att etiketten "Labels/Kvitton" finns
    And att mejlet med UID "42" och Message-ID "<a@x>" ligger i "INBOX"
    And att mejlet med Message-ID "<a@x>" har etiketten "Labels/Kvitton" med UID "7"
    And att Bridge nekar EXPUNGE med "backend error"
    When jag tar bort etiketten "Kvitton" från UID "42" i "INBOX"
    Then ska verktyget ge ett fel som nämner "backend error"
    And ska Bridge ha fått "UID STORE" med "7 -FLAGS (\Deleted)"
