Feature: Svar och vidarebefordran på ett mejl som inte finns ger ett handlingsbart fel
  Som modell som svarar på mejl
  vill jag få veta att UID:t inte finns i mappen
  i stället för ett tyst false, så att jag rättar mailbox i stället för att gissa.

  Scenario Outline: Ett UID från fel mapp
    Given att mappen "INBOX" inte har något mejl med UID "99"
    When jag anropar <verktyg> med uid "99" i mappen "INBOX"
    Then ska anropet misslyckas med texten "Inget meddelande med UID 99 i INBOX"
    And ska felet säga att UID:n gäller per mapp
    And ska inget mejl ha skickats

    Examples:
      | verktyg        |
      | reply_to_email |
      | forward_email  |
