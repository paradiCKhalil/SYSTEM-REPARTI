// Exemple original : "An Introduction to Network Programming with Java" Jan Graba; pp:25


import java.io.*;
import java.net.*;
import java.util.*;

public class TCPEchoClient
{
private static InetAddress host;
private static final int PORT = 1234;

public static void main(String[] args)
{
	try
	{
	  host = InetAddress.getLocalHost();
	  //host = InetAddress.getByName(null);	
	}
	catch(UnknownHostException uhEx)
	{
	System.out.println("Hôte non trouvé!");
	System.exit(1);
	}
	accessServer();
}

private static void accessServer()
{
	Socket link = null;//Step 1.
	try
	{
		link = new Socket(host,PORT);//Step 1.
		Scanner input = new Scanner(link.getInputStream()); //Step 2.
		PrintWriter output = new PrintWriter(link.getOutputStream(),true);//Step 2.
		//Set up stream for keyboard entry...
		Scanner userEntry = new Scanner(System.in);
		String message, response;
		do
		{
		System.out.print("Saisir un Message: ");
		message = userEntry.nextLine();
		output.println(message);//Step 3.
		response = input.nextLine();//Step 3.
		System.out.println("\nSERVER> "+response);
		}while (!message.equalsIgnoreCase("FIN"));
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
		link.close();//Step 4.
		}
		catch(IOException ioEx)
		{
		System.out.println("deconnexion impossible!");
		System.exit(1);
		}
	}
}
}
