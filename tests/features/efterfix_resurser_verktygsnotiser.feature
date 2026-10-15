Feature: Notiser när serverns egna verktyg ändrar brevlådan
  Som MCP-klient som prenumererar på en mapp, ett mejl eller mapplistan
  vill jag få en notis när serverns egna verktyg ändrar resursen
  (markerar, flyttar, raderar, etiketterar, skapar mappar, sparar utkast, skickar)
  så att jag inte visar inaktuell data efter något som gjordes i samma server.
  Ändringar som andra klienter gör (Proton-appen, webben) notifieras bara som
  nya mejl i de bevakade mapparna (PROTONMAIL_WATCH_MAILBOXES).

  Scenario: Markera som läst ger notis om mappen och mejlet
    Given att klienten prenumererar på "mailbox://INBOX, email://INBOX/42"
    When klienten anropar mark_email_read med uid "42" i mappen "INBOX"
    Then ska klienten få notiser om "mailbox://INBOX, email://INBOX/42"

  Scenario: Flytt ger notis om källmappen, målmappen och mejlet
    Given att klienten prenumererar på "mailbox://INBOX, mailbox://Archive, email://INBOX/42"
    When klienten anropar move_email med uid "42" från "INBOX" till "Archive"
    Then ska klienten få notiser om "mailbox://INBOX, mailbox://Archive, email://INBOX/42"

  Scenario: Radering till papperskorgen ger notis om mappen och Trash
    Given att klienten prenumererar på "mailbox://INBOX, mailbox://Trash"
    When klienten anropar delete_email med uid "42" i mappen "INBOX"
    Then ska klienten få notiser om "mailbox://INBOX, mailbox://Trash"

  Scenario: En ny mapp ger notis om mapplistan
    Given att klienten prenumererar på "mailboxes://"
    When klienten anropar create_folder med namnet "Folders/Kunder"
    Then ska klienten få notiser om "mailboxes://"

  Scenario: Namnbyte ger notis om mapplistan och båda mapparna
    Given att klienten prenumererar på "mailboxes://, mailbox://Folders%2FA, mailbox://Folders%2FB"
    When klienten byter namn på mappen "Folders/A" till "Folders/B"
    Then ska klienten få notiser om "mailboxes://, mailbox://Folders%2FA, mailbox://Folders%2FB"

  Scenario: Ett skickat mejl ger notis om Sent
    Given att klienten prenumererar på "mailbox://Sent"
    When klienten skickar ett mejl med send_email
    Then ska klienten få notiser om "mailbox://Sent"

  Scenario: Med en lista UID:n notifieras bara de som ändrades
    Given att klienten prenumererar på "mailbox://INBOX, email://INBOX/1, email://INBOX/2"
    And att markeringen lyckas för UID "1" men misslyckas för UID "2"
    When klienten anropar mark_email_read med uid-listan "1, 2" i mappen "INBOX"
    Then ska klienten få notiser om "mailbox://INBOX, email://INBOX/1"

  Scenario: Ett misslyckat verktygsanrop ger ingen notis
    Given att klienten prenumererar på "mailbox://INBOX, email://INBOX/42"
    And att Bridge nekar markeringen
    When klienten anropar mark_email_read med uid "42" i mappen "INBOX"
    Then ska anropet misslyckas
    And ska klienten inte få någon notis

  Scenario: Läsande verktyg ger ingen notis
    Given att klienten prenumererar på "mailbox://INBOX"
    When klienten anropar list_emails i mappen "INBOX"
    Then ska klienten inte få någon notis

  Scenario: En session som inte läser fördröjer inte verktygssvaret
    Given att klienten prenumererar på "mailbox://INBOX"
    And att notiserna till prenumeranterna hänger
    When klienten anropar mark_email_read med uid "42" i mappen "INBOX"
    Then ska verktygssvaret komma utan att vänta på notiserna

  Scenario: Resursbeskrivningarna säger vad som notifieras
    When klienten listar resursmallarna
    Then ska beskrivningen av "mailbox" nämna "PROTONMAIL_WATCH_MAILBOXES" och "andra klienter"
    And ska beskrivningen av "email" nämna "serverns egna verktyg" och "andra klienter"
