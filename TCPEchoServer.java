//Exemple original  : "An Introduction to Network Programming with Java" Jan Graba; pp:25


import java.io.*;
import java.net.*;
import java.util.*;
public class TCPEchoServer
{
	private static ServerSocket servSock;
	private static final int PORT = 1234;
	
	public static void main(String[] args)
	{
		
		try
		{    //PORT=Integer.parseInt(args[0]);
			servSock = new ServerSocket(PORT);//Step 1.
			System.out.println("Serveur Prêt : En attente de connexion...\n");
		}
		catch(IOException ioEx)
		{
			System.out.println("Probleme avec le numero de port!");
			System.exit(1);
		}
	
	    // Boucle infinie pour le service. On peut forcer l'arret
        // avec  CTRL-C 
		do
		{
			handleClient();
		}while (true);  // the server 
	
	}
	
	private static void handleClient()
	{
		Socket link = null;//Step 2.
		try
		{
			link = servSock.accept();//Step 2.

			Scanner input = new Scanner(link.getInputStream());//Step 3.
			PrintWriter output =new PrintWriter(link.getOutputStream(),true); //Step 3.

			int numMessages = 0;
			String message = input.nextLine();//Step 4.
			while (!message.equalsIgnoreCase("FIN"))
			{
			System.out.println("Message recu.");
			//System.out.println("Message reçu = " + message);
			numMessages++;
			output.println("Message  " + numMessages + ": " + message); //Step 4.
			message = input.nextLine();
			}
			output.println(numMessages + " messages reçus du client, en tout.");//Step 4.
		}
		catch(IOException ioEx)
		{
			ioEx.printStackTrace();
		}
		finally
		{
			try
			{
			System.out.println("\n* Fermeture connexion... *");
			link.close();//Step 5.
			}
			catch(IOException ioEx)
			{
			System.out.println("Erreur fermeture connexion!");
			System.exit(1);
			}
		}
	}
}



